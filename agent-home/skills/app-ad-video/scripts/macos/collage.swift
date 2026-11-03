import AppKit
// Labeled image grid (macOS): show options to the user (talent candidates, variants), reference vs ours
// side by side, contact sheets. Useful when ffmpeg is built without drawtext.
//   swiftc -O collage.swift -o bin/collage        (or: bash build.sh)
//   bin/collage <out.png> <cols> <cell_w> <cell_h> <label_h> 'path|Title\nsecond line' ...
// A label can have two lines: separate them with \n (inside single quotes so the shell leaves it alone).
let a = CommandLine.arguments
let out = a[1]; let cols = Int(a[2])!; let tw = CGFloat(Double(a[3])!); let th = CGFloat(Double(a[4])!); let lh = CGFloat(Double(a[5])!)
let items = a[6...].map { $0.components(separatedBy: "|") }
let rows = (items.count + cols - 1) / cols
let W = tw * CGFloat(cols), Hh = (th + lh) * CGFloat(rows)
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(W), pixelsHigh: Int(Hh), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSColor(calibratedRed: 0.10, green: 0.086, blue: 0.078, alpha: 1).setFill()
NSRect(x: 0, y: 0, width: W, height: Hh).fill()
for (i, it) in items.enumerated() {
  let r = i / cols, c = i % cols
  let x = CGFloat(c) * tw, yTop = CGFloat(r) * (th + lh)
  let y = Hh - yTop - th
  if let img = NSImage(contentsOfFile: it[0]), img.size.width > 0, img.size.height > 0 {
    // keep the aspect ratio (no stretched faces), centered in the cell
    let cw = tw - 8, ch = th - 8
    let k = min(cw / img.size.width, ch / img.size.height)
    let dw = img.size.width * k, dh = img.size.height * k
    img.draw(in: NSRect(x: x + 4 + (cw - dw) / 2, y: y + 4 + (ch - dh) / 2, width: dw, height: dh))
  }
  let p = NSMutableParagraphStyle(); p.alignment = .center
  let lines = it[1].components(separatedBy: "\\n")
  let attrs1: [NSAttributedString.Key: Any] = [.font: NSFont.boldSystemFont(ofSize: 26), .foregroundColor: NSColor.white, .paragraphStyle: p]
  let attrs2: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 20), .foregroundColor: NSColor(white: 0.85, alpha: 1), .paragraphStyle: p]
  NSAttributedString(string: lines[0], attributes: attrs1).draw(in: NSRect(x: x, y: y - 40, width: tw, height: 34))
  if lines.count > 1 { NSAttributedString(string: lines[1], attributes: attrs2).draw(in: NSRect(x: x, y: y - 70, width: tw, height: 28)) }
}
NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
print("wrote", out, Int(W), Int(Hh))
