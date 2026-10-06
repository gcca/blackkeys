import SwiftUI

/// The brand's stores, one row each, with a directions button that asks the
/// map to jump to the brand. Hidden when the brand has no stores.
struct BrandStoresSection: View {
    let brand: Brand
    let onShowDirections: (MapDestination) -> Void

    var body: some View {
        if !brand.stores.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Text("Tiendas")
                    .font(.title3.bold())

                ForEach(Array(brand.stores.enumerated()), id: \.offset) { _, store in
                    HStack(spacing: 12) {
                        Text(store.name.isEmpty ? brand.displayName : store.name)
                            .font(.subheadline)
                            .frame(maxWidth: .infinity, alignment: .leading)

                        Button("Cómo llegar") {
                            onShowDirections(MapDestination(brand: brand))
                        }
                        .buttonStyle(.glass)
                        .accessibilityIdentifier("brandViewStoreDirectionsButton-\(store.id)")
                    }
                }
            }
            .padding(.horizontal)
            .padding(.top, 24)
        }
    }
}

#Preview {
    BrandStoresSection(
        brand: Brand(
            name: "ADIDAS",
            displayName: "Adidas",
            description: "",
            isActive: true,
            kioskId: 12,
            amenities: [],
            stores: [
                Brand.Store(id: 4, name: "Corredor Mantaro, 2do nivel"),
                Brand.Store(id: 5, name: "Plaza Central, 1er nivel"),
            ],
            tags: []
        ),
        onShowDirections: { _ in }
    )
}
