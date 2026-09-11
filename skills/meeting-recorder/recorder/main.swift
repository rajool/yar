// MeetingRecorder — audio-only meeting recorder for macOS.
//
// Captures TWO sources and writes them as two lossless temp files:
//   1. System audio output (the remote meeting participants) via a CoreAudio
//      *process tap* (macOS 14.4+). Device-independent: works the same whether
//      you are on AirPods or the Mac speakers, because it taps the output
//      mix, not a specific device path.
//   2. The microphone (your own voice) via AVAudioEngine's input node.
//
// The two CAF files are mixed into one small AAC .m4a by ffmpeg in
// meet-recorder.sh (kept out of Swift so the risky native capture and the
// trivial muxing stay decoupled — see SKILL.md).
//
// Why a process tap and not ScreenCaptureKit: truly audio-only (no video
// pipeline), no Screen-Recording permission, and stable on macOS 26.1+.
//
// Stop cleanly with SIGINT/SIGTERM (the wrapper sends `kill -INT`). On stop we
// tear down the tap/aggregate/engine and close both files so their headers are
// finalized, then exit 0.
//
// Build: see build.sh (swiftc + embed Info.plist + ad-hoc codesign). The
// Info.plist usage-description keys (NSMicrophoneUsageDescription,
// NSAudioCaptureUsageDescription) drive the one-time TCC permission prompts.

import Foundation
import AVFoundation
import CoreAudio
import AudioToolbox

// MARK: - Logging (everything to stderr; stdout stays clean for paths)

func elog(_ msg: String) {
    FileHandle.standardError.write(Data(("[MeetingRecorder] " + msg + "\n").utf8))
}

enum RecError: Error, CustomStringConvertible {
    case ca(String, OSStatus)
    case msg(String)
    var description: String {
        switch self {
        case .ca(let what, let st): return "\(what) failed (OSStatus \(st))"
        case .msg(let m): return m
        }
    }
}

// MARK: - CoreAudio property helpers

func caAudioObjectID(_ obj: AudioObjectID, _ selector: AudioObjectPropertySelector) throws -> AudioObjectID {
    var addr = AudioObjectPropertyAddress(mSelector: selector,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var value = AudioObjectID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    let st = AudioObjectGetPropertyData(obj, &addr, 0, nil, &size, &value)
    guard st == noErr else { throw RecError.ca("get property \(selector)", st) }
    return value
}

func caString(_ obj: AudioObjectID, _ selector: AudioObjectPropertySelector) throws -> String {
    var addr = AudioObjectPropertyAddress(mSelector: selector,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var size = UInt32(0)
    var st = AudioObjectGetPropertyDataSize(obj, &addr, 0, nil, &size)
    guard st == noErr else { throw RecError.ca("get size \(selector)", st) }
    // CFString properties return a +1 reference; takeRetainedValue() balances it.
    var cf: Unmanaged<CFString>?
    st = withUnsafeMutablePointer(to: &cf) {
        AudioObjectGetPropertyData(obj, &addr, 0, nil, &size, $0)
    }
    guard st == noErr, let value = cf?.takeRetainedValue() else {
        throw RecError.ca("get string \(selector)", st)
    }
    return value as String
}

func defaultSystemOutputDevice() throws -> AudioObjectID {
    let dev = try caAudioObjectID(AudioObjectID(kAudioObjectSystemObject),
                                  kAudioHardwarePropertyDefaultSystemOutputDevice)
    guard dev != AudioObjectID(kAudioObjectUnknown) else {
        throw RecError.msg("no default system output device")
    }
    return dev
}

// MARK: - Recorder

final class Recorder {
    private let systemURL: URL
    private let micURL: URL?
    private let monoTap: Bool

    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private let ioQueue = DispatchQueue(label: "io.yar.meetingrecorder.tap")
    private var systemFile: AVAudioFile?

    private let engine = AVAudioEngine()
    private var micFile: AVAudioFile?
    private var micActive = false

    private var stopped = false
    private let stopLock = NSLock()

    init(systemURL: URL, micURL: URL?, monoTap: Bool) {
        self.systemURL = systemURL
        self.micURL = micURL
        self.monoTap = monoTap
    }

    // MARK: System audio (process tap → aggregate device → IOProc → file)

    func startSystemCapture() throws {
        let outputDevice = try defaultSystemOutputDevice()
        let outputUID = try caString(outputDevice, kAudioDevicePropertyDeviceUID)

        // Global tap of all processes' output (exclude none = everything we hear).
        let tapDescription = monoTap
            ? CATapDescription(monoGlobalTapButExcludeProcesses: [])
            : CATapDescription(stereoGlobalTapButExcludeProcesses: [])
        tapDescription.uuid = UUID()
        tapDescription.name = "MeetingRecorderTap"
        tapDescription.muteBehavior = .unmuted          // don't alter what the user hears
        tapDescription.isPrivate = true                 // not visible to other apps

        var newTap = AudioObjectID(kAudioObjectUnknown)
        let tapStatus = AudioHardwareCreateProcessTap(tapDescription, &newTap)
        guard tapStatus == noErr, newTap != AudioObjectID(kAudioObjectUnknown) else {
            throw RecError.ca("AudioHardwareCreateProcessTap (grant 'Audio Recording' / 'System Audio Recording' in System Settings > Privacy)", tapStatus)
        }
        tapID = newTap

        // Read the tap's stream format so the output file matches exactly.
        var asbd = AudioStreamBasicDescription()
        var fmtAddr = AudioObjectPropertyAddress(mSelector: kAudioTapPropertyFormat,
                                                 mScope: kAudioObjectPropertyScopeGlobal,
                                                 mElement: kAudioObjectPropertyElementMain)
        var fmtSize = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        let fmtStatus = AudioObjectGetPropertyData(tapID, &fmtAddr, 0, nil, &fmtSize, &asbd)
        guard fmtStatus == noErr, let tapFormat = AVAudioFormat(streamDescription: &asbd) else {
            throw RecError.ca("read tap format", fmtStatus)
        }
        elog(String(format: "tap format: %.0f Hz, %u ch", tapFormat.sampleRate, tapFormat.channelCount))

        // Wrap the tap in a private aggregate device so we can attach an IOProc.
        let aggregateUID = UUID().uuidString
        let description: [String: Any] = [
            kAudioAggregateDeviceNameKey: "MeetingRecorderAggregate",
            kAudioAggregateDeviceUIDKey: aggregateUID,
            kAudioAggregateDeviceMainSubDeviceKey: outputUID,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceSubDeviceListKey: [
                [kAudioSubDeviceUIDKey: outputUID]
            ],
            kAudioAggregateDeviceTapListKey: [
                [
                    kAudioSubTapDriftCompensationKey: true,
                    kAudioSubTapUIDKey: tapDescription.uuid.uuidString
                ]
            ]
        ]
        var newAgg = AudioObjectID(kAudioObjectUnknown)
        let aggStatus = AudioHardwareCreateAggregateDevice(description as CFDictionary, &newAgg)
        guard aggStatus == noErr, newAgg != AudioObjectID(kAudioObjectUnknown) else {
            throw RecError.ca("AudioHardwareCreateAggregateDevice", aggStatus)
        }
        aggregateID = newAgg

        // Open the output file in the tap's exact format (lossless CAF).
        systemFile = try AVAudioFile(forWriting: systemURL,
                                     settings: tapFormat.settings,
                                     commonFormat: tapFormat.commonFormat,
                                     interleaved: tapFormat.isInterleaved)

        // IOProc runs on our serial queue (not the realtime thread) so file
        // writes are safe.
        let writeFormat = tapFormat
        var procID: AudioDeviceIOProcID?
        let procStatus = AudioDeviceCreateIOProcIDWithBlock(&procID, aggregateID, ioQueue) {
            [weak self] (_, inInputData, _, _, _) in
            guard let self = self, let file = self.systemFile else { return }
            guard let buffer = AVAudioPCMBuffer(pcmFormat: writeFormat,
                                                bufferListNoCopy: inInputData,
                                                deallocator: nil) else { return }
            do { try file.write(from: buffer) } catch { /* drop a frame; keep going */ }
        }
        guard procStatus == noErr, let proc = procID else {
            throw RecError.ca("AudioDeviceCreateIOProcIDWithBlock", procStatus)
        }
        ioProcID = proc

        let startStatus = AudioDeviceStart(aggregateID, proc)
        guard startStatus == noErr else { throw RecError.ca("AudioDeviceStart", startStatus) }
        elog("system-audio capture started → \(systemURL.lastPathComponent)")
    }

    // MARK: Microphone (AVAudioEngine input node → file)

    func startMicCapture() {
        guard let micURL = micURL else { elog("mic disabled (--no-mic)"); return }

        func begin() {
            let input = engine.inputNode
            let format = input.outputFormat(forBus: 0)
            guard format.channelCount > 0, format.sampleRate > 0 else {
                elog("mic unavailable (no input channels) — continuing system-only")
                return
            }
            do {
                let file = try AVAudioFile(forWriting: micURL,
                                           settings: format.settings,
                                           commonFormat: format.commonFormat,
                                           interleaved: format.isInterleaved)
                self.micFile = file
                input.installTap(onBus: 0, bufferSize: 4096, format: format) { buffer, _ in
                    do { try file.write(from: buffer) } catch { /* keep going */ }
                }
                engine.prepare()
                try engine.start()
                self.micActive = true
                elog(String(format: "mic capture started → %@ (%.0f Hz, %u ch)",
                            micURL.lastPathComponent, format.sampleRate, format.channelCount))
            } catch {
                elog("mic capture failed: \(error) — continuing system-only")
            }
        }

        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            begin()
        case .notDetermined:
            elog("requesting microphone permission…")
            AVCaptureDevice.requestAccess(for: .audio) { granted in
                if granted { begin() }
                else { elog("microphone permission denied — continuing system-only") }
            }
        default:
            elog("microphone permission not granted (System Settings > Privacy > Microphone) — continuing system-only")
        }
    }

    // MARK: Stop / teardown

    func stop() {
        stopLock.lock(); defer { stopLock.unlock() }
        guard !stopped else { return }
        stopped = true
        elog("stopping…")

        if let proc = ioProcID {
            AudioDeviceStop(aggregateID, proc)
            AudioDeviceDestroyIOProcID(aggregateID, proc)
            ioProcID = nil
        }
        if aggregateID != AudioObjectID(kAudioObjectUnknown) {
            AudioHardwareDestroyAggregateDevice(aggregateID)
            aggregateID = AudioObjectID(kAudioObjectUnknown)
        }
        if tapID != AudioObjectID(kAudioObjectUnknown) {
            AudioHardwareDestroyProcessTap(tapID)
            tapID = AudioObjectID(kAudioObjectUnknown)
        }
        // Flush any in-flight tap write, then close the file (finalizes header).
        ioQueue.sync { self.systemFile = nil }

        if micActive {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }
        micFile = nil

        elog("done")
        if micActive, let m = micURL { print(m.path) }
        print(systemURL.path)
    }
}

// MARK: - Argument parsing

func usage() -> Never {
    FileHandle.standardError.write(Data("""
    MeetingRecorder — audio-only meeting recorder

    Usage:
      MeetingRecorder --system <path.caf> [--mic <path.caf> | --no-mic]
                      [--mono-tap] [--max-seconds N]

    Records system audio (process tap) and microphone to two CAF files.
    Stop with SIGINT/SIGTERM. Paths are printed to stdout on stop.
    """.utf8))
    exit(64)
}

var systemPath: String?
var micPath: String?
var noMic = false
var monoTap = false
var maxSeconds: Double?

var args = Array(CommandLine.arguments.dropFirst())
var i = 0
while i < args.count {
    let a = args[i]
    switch a {
    case "--system": i += 1; systemPath = i < args.count ? args[i] : nil
    case "--mic":    i += 1; micPath = i < args.count ? args[i] : nil
    case "--no-mic": noMic = true
    case "--mono-tap": monoTap = true
    case "--max-seconds": i += 1; maxSeconds = i < args.count ? Double(args[i]) : nil
    case "-h", "--help": usage()
    default: FileHandle.standardError.write(Data("unknown argument: \(a)\n".utf8)); usage()
    }
    i += 1
}

guard let systemPath = systemPath else { usage() }
let systemURL = URL(fileURLWithPath: systemPath)
let micURL: URL? = noMic ? nil : (micPath.map { URL(fileURLWithPath: $0) }
    ?? systemURL.deletingLastPathComponent().appendingPathComponent("mic.caf"))

let recorder = Recorder(systemURL: systemURL, micURL: micURL, monoTap: monoTap)

do {
    try recorder.startSystemCapture()
} catch {
    elog("FATAL: \(error)")
    exit(1)
}
recorder.startMicCapture()

// Signal-driven clean stop.
signal(SIGINT, SIG_IGN)
signal(SIGTERM, SIG_IGN)
let signalQueue = DispatchQueue(label: "io.yar.meetingrecorder.signals")
let sigint = DispatchSource.makeSignalSource(signal: SIGINT, queue: signalQueue)
let sigterm = DispatchSource.makeSignalSource(signal: SIGTERM, queue: signalQueue)
let onSignal: () -> Void = { recorder.stop(); exit(0) }
sigint.setEventHandler(handler: onSignal)
sigterm.setEventHandler(handler: onSignal)
sigint.resume()
sigterm.resume()

if let maxSeconds = maxSeconds {
    elog("auto-stop in \(maxSeconds)s")
    signalQueue.asyncAfter(deadline: .now() + maxSeconds) { recorder.stop(); exit(0) }
}

elog("recording… (stop with SIGINT/SIGTERM)")
dispatchMain()
