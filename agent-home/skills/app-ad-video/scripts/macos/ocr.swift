import Foundation
import Vision
import AppKit

// On-screen text OCR (macOS Vision): reads captions/labels in references and the text in deliveries.
//   swiftc -O ocr.swift -o bin/ocr        (or: bash build.sh)
//   bin/ocr <png_dir_or_png...> [--lang en-US,es-ES,pt-BR,de-DE]
// Output (one line per file):  name<TAB>text|x,y,w,h ;; text|x,y,w,h ...
//   boxes are NORMALIZED with a BOTTOM-LEFT origin (Vision): pixel top = (1 - y - h) * H
// Careful: Cyrillic homoglyphs and c/o can get mixed up. If a critical frame reads wrong,
// crop it and check by eye.
var args = Array(CommandLine.arguments.dropFirst())
var langs = ["en-US", "es-ES", "pt-BR", "de-DE", "fr-FR"]
if let i = args.firstIndex(of: "--lang"), i + 1 < args.count {
    langs = args[i + 1].components(separatedBy: ",")
    args.removeSubrange(i...(i + 1))
}
var files: [String] = []
for a in args {
    var isDir: ObjCBool = false
    if FileManager.default.fileExists(atPath: a, isDirectory: &isDir), isDir.boolValue {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: a)) ?? []
        files += names.filter { $0.lowercased().hasSuffix(".png") || $0.lowercased().hasSuffix(".jpg") }
            .sorted().map { (a as NSString).appendingPathComponent($0) }
    } else {
        files.append(a)
    }
}
for path in files {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    req.recognitionLanguages = langs
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    var parts: [String] = []
    for o in req.results ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        parts.append(String(format: "%@|%.4f,%.4f,%.4f,%.4f", c.string, b.origin.x, b.origin.y, b.size.width, b.size.height))
    }
    print("\((path as NSString).lastPathComponent)\t\(parts.joined(separator: " ;; "))")
}
