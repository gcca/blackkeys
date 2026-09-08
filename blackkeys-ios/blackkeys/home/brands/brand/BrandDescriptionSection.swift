import SwiftUI

struct BrandDescriptionSection: View {
    let brand: Brand

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Descubre \(brand.displayName)")
                .font(.title3.bold())

            if !brand.description.isEmpty {
                Text(brand.description)
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal)
        .padding(.top, 20)
    }
}
