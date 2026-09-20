import SwiftUI
import WebKit

enum MapGeolocationPermissionPolicy {
    static let trustedProtocol = "https"
    static let trustedHost = "demos.mappedin.com"
    static let defaultHTTPSPort = 443

    // WKSecurityOrigin reports port 0 for a URL's default port (e.g. an
    // https:// origin with no explicit port), not 443, so both must be
    // accepted as "the trusted origin's default port".
    static func decision(forProtocol scheme: String, host: String, port: Int) -> WKPermissionDecision {
        guard scheme == trustedProtocol, host == trustedHost, port == 0 || port == defaultHTTPSPort else {
            return .deny
        }
        return .prompt
    }
}

struct MapView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView(frame: .zero)
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.uiDelegate = context.coordinator
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        // Static URL; nothing to react to.
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    final class Coordinator: NSObject, WKUIDelegate {
        func webView(
            _ webView: WKWebView,
            requestGeolocationPermissionFor origin: WKSecurityOrigin,
            initiatedByFrame frame: WKFrameInfo,
            decisionHandler: @escaping (WKPermissionDecision) -> Void
        ) {
            decisionHandler(
                MapGeolocationPermissionPolicy.decision(
                    forProtocol: origin.protocol,
                    host: origin.host,
                    port: origin.port
                )
            )
        }
    }
}

#Preview {
    MapView(url: URL(string: "https://demos.mappedin.com/web/mappedin-web/plaza-san-miguel/plaza-san-miguel.html")!)
        .ignoresSafeArea()
}
