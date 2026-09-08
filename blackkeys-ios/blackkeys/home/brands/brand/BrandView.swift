import SwiftUI

/// Detail screen opened when a brand card is tapped (see `BrandsView`'s
/// `.sheet(item:)`). Reuses `BrandCardImage`'s cache-first loading for both
/// the cover photo and the logo, and `BrandPresentation`'s deterministic tint
/// so the detail screen matches the card the user tapped.
struct BrandView: View {
    let item: BrandPresentation

    @Environment(\.dismiss) private var dismiss
    @State private var isFavorite = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                BrandCoverHeader(item: item, isFavorite: $isFavorite, onBack: { dismiss() })

                BrandInfoSection(item: item)
                    .padding(.top, BrandCoverHeader.logoOverlap)

                BrandDescriptionSection(brand: item.brand)
            }
        }
        .ignoresSafeArea(edges: .top)
        .presentationDragIndicator(.hidden)
        .presentationDetents([.large])
    }
}

#Preview {
    BrandView(item: BrandPresentation(brand: Brand(
        name: "ADIDAS",
        displayName: "Adidas",
        logoUrl: URL(string: "https://example.com/logo.png"),
        pictureUrl: URL(string: "https://example.com/picture.jpg"),
        description: "Encuentra las últimas colecciones de calzado y ropa deportiva para toda la familia.",
        isActive: true,
        kioskId: 12,
        amenities: [],
        stores: [Brand.Store(id: 4, name: "Corredor Mantaro, 2do nivel")],
        tags: ["Tienda por departamento"]
    )))
}
