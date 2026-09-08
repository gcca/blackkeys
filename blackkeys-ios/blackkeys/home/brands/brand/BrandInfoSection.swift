import SwiftUI

/// Eyebrow/title/subtitle text block plus the primary "Cómo llegar" action.
/// The button is rendered for visual parity with the reference design but is
/// intentionally inert — this app has no MapKit/Mappedin wiring yet.
struct BrandInfoSection: View {
    let item: BrandPresentation

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                if let category = item.brand.tags.first {
                    Text(category.uppercased())
                        .font(.caption.weight(.bold))
                        .tracking(1)
                        .foregroundStyle(item.tint)
                }

                Text(item.brand.displayName)
                    .font(.largeTitle.bold())

                Text(BrandDetailFormatting.subtitle(for: item.brand))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            GlassEffectContainer {
                Button("Cómo llegar") {}
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
                    .buttonStyle(.glassProminent)
                    .accessibilityIdentifier("brandViewDirectionsButton")
            }
        }
        .padding(.horizontal)
    }
}
