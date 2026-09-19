import SwiftUI

struct HomeView: View {
    let session: AuthSession

    @State private var searchText = ""
    @State private var isShowingStores = false

    private var mapURL: URL {
        URL(string: "https://demos.mappedin.com/web/mappedin-web/plaza-san-miguel/plaza-san-miguel.html")!
    }

    var body: some View {
        MapView(url: mapURL)
            .ignoresSafeArea()
            .overlay(alignment: .bottom) {
                exploreFooter
                    .padding(.horizontal)
                    .padding(.bottom, 8)
            }
            .sheet(isPresented: $isShowingStores) {
                StoresView()
            }
    }

    private var exploreFooter: some View {
        GlassEffectContainer(spacing: 12) {
            HStack(spacing: 12) {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)
                    TextField("Search Plaza San Miguel", text: $searchText)
                        .textInputAutocapitalization(.never)
                        .accessibilityIdentifier("storeSearchTextField")
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .glassEffect(in: .capsule)

                Button {
                    isShowingStores = true
                } label: {
                    Image(systemName: "square.grid.2x2")
                        .font(.title3)
                        .frame(width: 44, height: 44)
                }
                .buttonStyle(.glass)
                .accessibilityIdentifier("exploreStoresButton")
                .accessibilityLabel("Explore stores")
            }
        }
    }
}

#Preview {
    HomeView(session: AuthSession(username: "alex", token: "preview-token"))
}
