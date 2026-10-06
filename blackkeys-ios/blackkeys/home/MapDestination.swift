import Foundation

/// A place on the Mappedin map that the user asked to jump to, e.g. from a
/// brand's store row. `requestID` is fresh for every request, so asking for
/// the same place twice still counts as a new request (the user may have
/// moved the map elsewhere in between).
struct MapDestination: Equatable, Sendable {
    let identifier: String
    let requestID = UUID()

    init(identifier: String) {
        self.identifier = identifier
    }

    /// Single place that decides which brand field Mappedin is asked to
    /// resolve. `displayName` is the best guess for a Mappedin location name;
    /// switch it here if the map turns out to expect an id or an external id.
    init(brand: Brand) {
        self.init(identifier: brand.displayName)
    }
}

/// Builds the Mappedin Web page URLs. The hosted page uses hash routes
/// (`#/directions?to=…`, `#/profile?location=…`), see
/// https://developer.mappedin.com/docs/enterprise-apps/mappedin-web/deep-linking.
/// Every URL stays on `demos.mappedin.com`, the host the geolocation policy
/// in `MapView` trusts.
enum MapRoute {
    static let baseURL = URL(string: "https://demos.mappedin.com/web/mappedin-web/plaza-san-miguel/plaza-san-miguel.html")!

    enum Kind {
        /// Route to the place. No departure is given, so the page asks for one
        /// (or uses the Blue Dot).
        case directions
        /// The place's own page, without a route.
        case profile

        fileprivate var fragment: (path: String, parameter: String) {
            switch self {
            case .directions: ("/directions", "to")
            case .profile: ("/profile", "location")
            }
        }
    }

    static func url(base: URL = baseURL, destination: MapDestination?, kind: Kind = .directions) -> URL {
        guard
            let destination,
            var components = URLComponents(url: base, resolvingAgainstBaseURL: false)
        else {
            return base
        }

        let route = kind.fragment
        // `percentEncodedFragment`: `URLComponents` would leave `&`, `=`, `+`
        // and `/` raw inside a fragment, so the value is encoded by hand.
        components.percentEncodedFragment = "\(route.path)?\(route.parameter)=\(encode(destination.identifier))"
        return components.url ?? base
    }

    private static let unreserved = CharacterSet(
        charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    )

    private static func encode(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: unreserved) ?? ""
    }
}
