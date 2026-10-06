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
    /// Changes whenever a new jump is requested, so asking for the same `url`
    /// again still navigates (the user may have moved elsewhere in the map).
    var navigationID: UUID?

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView(frame: .zero)
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.uiDelegate = context.coordinator
        context.coordinator.markLoaded(url: url, navigationID: navigationID)
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        // Re-renders with an unchanged url/navigationID never reload the page.
        // A new request does: the Mappedin routes live in the URL fragment, so
        // loading the same page with a different fragment is a same-document
        // navigation (`hashchange`), not a page reload.
        if context.coordinator.needsLoad(url: url, navigationID: navigationID) {
            context.coordinator.markLoaded(url: url, navigationID: navigationID)
            uiView.load(URLRequest(url: url))
        }

        // The web page's own scrollable content (map canvas, attribution)
        // starts at its viewport's top edge, unaware of the notch/status bar
        // the full-bleed WKWebView extends under. Insetting only the scroll
        // content (not the view's frame or background) pushes it clear while
        // keeping the map's edge-to-edge look — a transparent gap rather than
        // an opaque bar. This does NOT reach the page's own `position: fixed`
        // bottom sheet (confirmed in Mappedin's bundle) — that only responds
        // to the WKWebView's actual frame shrinking. The native tab bar's
        // safe area provides that bottom clearance in HomeView.
        let topInset = uiView.safeAreaInsets.top
        guard uiView.scrollView.contentInset.top != topInset else { return }
        uiView.scrollView.contentInset.top = topInset
        uiView.scrollView.verticalScrollIndicatorInsets.top = topInset
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    final class Coordinator: NSObject, WKUIDelegate {
        private var loadedURL: URL?
        private var loadedNavigationID: UUID?

        func needsLoad(url: URL, navigationID: UUID?) -> Bool {
            url != loadedURL || navigationID != loadedNavigationID
        }

        func markLoaded(url: URL, navigationID: UUID?) {
            loadedURL = url
            loadedNavigationID = navigationID
        }

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
    MapView(url: MapRoute.baseURL)
        .ignoresSafeArea()
}
