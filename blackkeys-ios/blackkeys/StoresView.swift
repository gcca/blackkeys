import SwiftUI

struct StoresView: View {
    private let stores = [
        ("Apple Store", "apple.logo"),
        ("Bookstore", "book"),
        ("Coffee Shop", "cup.and.saucer"),
        ("Electronics", "tv"),
        ("Fashion", "tshirt"),
        ("Fitness", "figure.run"),
        ("Grocery", "cart"),
        ("Jewelry", "diamond"),
        ("Pharmacy", "cross.case"),
        ("Restaurant", "fork.knife"),
        ("Shoes", "shoe"),
        ("Toys", "gamecontroller"),
    ]

    private let columns = [GridItem(.adaptive(minimum: 90), spacing: 16)]

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: columns, spacing: 20) {
                    ForEach(stores, id: \.0) { store in
                        Button {
                            // Placeholder: no real action for demo stores.
                        } label: {
                            VStack(spacing: 8) {
                                Image(systemName: store.1)
                                    .font(.title2)
                                    .frame(width: 56, height: 56)
                                    .background(.fill.tertiary, in: .circle)
                                Text(store.0)
                                    .font(.caption)
                                    .multilineTextAlignment(.center)
                                    .lineLimit(2)
                            }
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(.primary)
                    }
                }
                .padding()
            }
            .navigationTitle("Explore")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }
}

#Preview {
    StoresView()
}
