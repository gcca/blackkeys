import SwiftUI

struct SearchView: View {
    let destination: MapDestination?

    init(destination: MapDestination? = nil) {
        self.destination = destination
    }

    var body: some View {
        MapView(
            url: MapRoute.url(destination: destination),
            navigationID: destination?.requestID
        )
        .ignoresSafeArea(edges: .top)
    }
}

#Preview {
    SearchView()
}
