import SwiftUI

/// View-local display mapping from a fetched `Brand` to the values its cards
/// render. `tint`/`imageHeight` are deterministic, seeded by `brand.name` (not
/// fixed, not fresh-random-per-render): the same brand always looks the same,
/// and the feed keeps visual variety without inventing per-brand backend
/// fields for it.
struct BrandPresentation: Identifiable {
    private static let tints: [Color] = [.indigo, .red, .brown, .teal, .yellow, .blue, .orange, .purple]
    private static let feedImageHeights: [CGFloat] = [110, 130, 150, 160, 170, 180, 190]

    var id: String { brand.name }
    let brand: Brand
    let secondaryText: String
    let tint: Color
    let imageHeight: CGFloat

    init(brand: Brand, imageHeight: CGFloat? = nil) {
        self.brand = brand

        if !brand.description.isEmpty {
            secondaryText = brand.description
        } else if !brand.tags.isEmpty {
            secondaryText = brand.tags.joined(separator: ", ")
        } else {
            secondaryText = ""
        }

        tint = Self.tints[Self.seededIndex(for: brand.name, salt: "tint", count: Self.tints.count)]
        self.imageHeight = imageHeight ?? Self.feedImageHeights[
            Self.seededIndex(for: brand.name, salt: "height", count: Self.feedImageHeights.count)
        ]
    }

    /// FNV-1a over the salted name, not `String.hashValue` — Swift's string
    /// hash is seeded randomly per process launch (hash-flooding protection),
    /// so it can't give a value that's stable across launches or testable.
    private static func seededIndex(for name: String, salt: String, count: Int) -> Int {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for byte in (name + "#" + salt).utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x0000_0100_0000_01b3
        }
        return Int(hash % UInt64(count))
    }
}
