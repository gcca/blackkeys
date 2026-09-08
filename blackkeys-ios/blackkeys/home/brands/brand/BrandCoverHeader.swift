import SwiftUI

/// Cover photo with back/favorite buttons overlaid, plus a circular logo
/// badge straddling the photo's bottom edge. `BrandCardImage` (from
/// `BrandCards.swift`) is reused unchanged for both images — it's already
/// keyed generically by `URL` via `BrandImageCache`, so a cache hit from the
/// card grid renders instantly here too, with no spinner.
struct BrandCoverHeader: View {
    static let logoDiameter: CGFloat = 72
    static let logoOverlap: CGFloat = logoDiameter / 2 + 8

    let item: BrandPresentation
    @Binding var isFavorite: Bool
    let onBack: () -> Void

    private static let coverHeight: CGFloat = 300

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            coverPhoto
            logoBadge
                .offset(x: 20, y: Self.logoDiameter / 2)
        }
    }

    private var coverPhoto: some View {
        BrandCardImage(url: item.brand.pictureUrl, tint: item.tint)
            .frame(maxWidth: .infinity)
            .frame(height: Self.coverHeight)
            .clipped()
            .overlay(alignment: .topLeading) {
                circleButton(systemImage: "chevron.left", accessibilityIdentifier: "brandViewBackButton", action: onBack)
                    .padding(.leading)
            }
            .overlay(alignment: .topTrailing) {
                circleButton(
                    systemImage: isFavorite ? "heart.fill" : "heart",
                    accessibilityIdentifier: "brandViewFavoriteButton"
                ) {
                    isFavorite.toggle()
                }
                .padding(.trailing)
            }
    }

    private var logoBadge: some View {
        BrandCardImage(url: item.brand.logoUrl, tint: item.tint)
            .frame(width: Self.logoDiameter, height: Self.logoDiameter)
            .clipShape(Circle())
            .overlay {
                Circle().strokeBorder(.background, lineWidth: 4)
            }
    }

    private func circleButton(systemImage: String, accessibilityIdentifier: String, action: @escaping () -> Void) -> some View {
        GlassEffectContainer {
            Button(action: action) {
                Image(systemName: systemImage)
                    .frame(width: 36, height: 36)
            }
            .buttonStyle(.glass)
            .clipShape(Circle())
            .accessibilityIdentifier(accessibilityIdentifier)
        }
    }
}
