import SwiftUI
import WebKit

struct MapView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView(frame: .zero)
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        // Static URL; nothing to react to.
    }
}

#Preview {
    MapView(url: URL(string: "https://demos.mappedin.com/web/mappedin-web/plaza-san-miguel/plaza-san-miguel.html")!)
        .ignoresSafeArea()
}
