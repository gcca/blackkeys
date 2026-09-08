import SwiftUI

struct SearchView: View {
    private let mapURL = URL(string: "https://demos.mappedin.com/web/mappedin-web/plaza-san-miguel/plaza-san-miguel.html")!

    var body: some View {
        MapView(url: mapURL)
            .ignoresSafeArea(edges: .top)
    }
}

#Preview {
    SearchView()
}
