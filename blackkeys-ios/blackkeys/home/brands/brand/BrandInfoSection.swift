import SwiftUI

/// Eyebrow/title/subtitle text block. The directions actions live with each
/// store in `BrandStoresSection`.
struct BrandInfoSection: View {
    let item: BrandPresentation

    var body: some View {
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
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal)
    }
}
