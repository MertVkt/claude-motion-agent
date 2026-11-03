// facetrack: face landmarks for a folder of PNG frames with Apple Vision (macOS).
//   swiftc -O facetrack.swift -o bin/facetrack        (or: bash build.sh)
//   bin/facetrack <frames_dir> <out.json>
// One JSON record per frame: found, bbox, roll, yaw and landmark groups, in pixels with a top-left origin.
import Foundation
import Vision
import AppKit

struct FaceOut: Codable {
    var frame: Int
    var found: Bool
    var bbox: [Double]?      // x, y, w, h: pixels, top-left origin
    var roll: Double?
    var yaw: Double?
    var contour: [[Double]]?
    var leftEye: [[Double]]?
    var rightEye: [[Double]]?
    var outerLips: [[Double]]?
    var innerLips: [[Double]]?
    var nose: [[Double]]?
    // extra groups for face HUD meshes: brows, nose crest, median line, pupils
    var leftEyebrow: [[Double]]?
    var rightEyebrow: [[Double]]?
    var noseCrest: [[Double]]?
    var medianLine: [[Double]]?
    var leftPupil: [[Double]]?
    var rightPupil: [[Double]]?
}

func flip(_ pts: [CGPoint], _ h: CGFloat) -> [[Double]] {
    pts.map { [Double($0.x), Double(h - $0.y)] }
}

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: facetrack <frames_dir> <out.json>\n".data(using: .utf8)!)
    exit(2)
}
let dir = args[1], outPath = args[2]

let files = try FileManager.default.contentsOfDirectory(atPath: dir)
    .filter { $0.hasSuffix(".png") }.sorted()

var results: [FaceOut] = []

for (i, f) in files.enumerated() {
    let url = URL(fileURLWithPath: dir).appendingPathComponent(f)
    guard let img = NSImage(contentsOf: url),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        results.append(FaceOut(frame: i, found: false)); continue
    }
    let W = CGFloat(cg.width), H = CGFloat(cg.height)
    let req = VNDetectFaceLandmarksRequest()
    let handler = VNImageRequestHandler(cgImage: cg, orientation: .up, options: [:])
    do { try handler.perform([req]) } catch {
        results.append(FaceOut(frame: i, found: false)); continue
    }
    guard let obs = (req.results as? [VNFaceObservation])?
            .max(by: { $0.boundingBox.width * $0.boundingBox.height
                     < $1.boundingBox.width * $1.boundingBox.height }) else {
        results.append(FaceOut(frame: i, found: false)); continue
    }

    // boundingBox: normalized, bottom-left origin -> pixels, top-left origin
    let bb = obs.boundingBox
    let px = Double(bb.origin.x * W)
    let pw = Double(bb.width * W)
    let ph = Double(bb.height * H)
    let py = Double((1 - bb.origin.y - bb.height) * H)

    var o = FaceOut(frame: i, found: true, bbox: [px, py, pw, ph],
                    roll: obs.roll?.doubleValue, yaw: obs.yaw?.doubleValue)
    if let lm = obs.landmarks {
        if let c = lm.faceContour { o.contour  = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.leftEye    { o.leftEye  = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.rightEye   { o.rightEye = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.outerLips  { o.outerLips = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.innerLips  { o.innerLips = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.nose       { o.nose     = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.leftEyebrow  { o.leftEyebrow  = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.rightEyebrow { o.rightEyebrow = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.noseCrest    { o.noseCrest    = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.medianLine   { o.medianLine   = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.leftPupil    { o.leftPupil    = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
        if let c = lm.rightPupil   { o.rightPupil   = flip(c.pointsInImage(imageSize: CGSize(width: W, height: H)), H) }
    }
    results.append(o)
}

let enc = JSONEncoder()
try enc.encode(results).write(to: URL(fileURLWithPath: outPath))
let ok = results.filter { $0.found }.count
FileHandle.standardError.write("face found in \(ok)/\(results.count) frames\n".data(using: .utf8)!)
