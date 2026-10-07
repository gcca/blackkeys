import Foundation
import Testing
@testable import blackkeys

@Suite
struct MapRouteTests {
    @Test func noDestinationKeepsTheBaseURL() {
        #expect(MapRoute.url(destination: nil) == MapRoute.baseURL)
    }

    @Test func directionsPutsTheDestinationInTheHashRoute() {
        let url = MapRoute.url(destination: MapDestination(identifier: "Adidas"))

        #expect(url.absoluteString == MapRoute.baseURL.absoluteString + "#/directions?to=Adidas")
    }

    @Test func profileUsesTheLocationParameter() {
        let url = MapRoute.url(destination: MapDestination(identifier: "Adidas"), kind: .profile)

        #expect(url.absoluteString == MapRoute.baseURL.absoluteString + "#/profile?location=Adidas")
    }

    @Test func reservedAndNonASCIICharactersAreEscapedInTheValue() {
        let url = MapRoute.url(destination: MapDestination(identifier: "A&B =C+D#E/F ñ"))

        #expect(url.fragment == "/directions?to=A%26B%20%3DC%2BD%23E%2FF%20%C3%B1")
    }

    @Test func theBasePageStaysOnTheTrustedGeolocationHost() {
        let url = MapRoute.url(destination: MapDestination(identifier: "Adidas"))

        #expect(url.scheme == MapGeolocationPermissionPolicy.trustedProtocol)
        #expect(url.host == MapGeolocationPermissionPolicy.trustedHost)
        #expect(url.path == MapRoute.baseURL.path)
    }

    @Test func aBrandIsResolvedByItsDisplayName() {
        let brand = Brand(
            name: "ADIDAS",
            displayName: "Adidas",
            description: "",
            isActive: true,
            kioskId: 12,
            amenities: [],
            stores: [Brand.Store(id: 4, name: "Corredor Mantaro, 2do nivel")],
            tags: []
        )

        #expect(MapDestination(brand: brand).identifier == "Adidas")
    }

    @Test func eachRequestForTheSamePlaceIsADistinctRequest() {
        let first = MapDestination(identifier: "Adidas")
        let second = MapDestination(identifier: "Adidas")

        #expect(first.identifier == second.identifier)
        #expect(first != second)
        #expect(first.requestID != second.requestID)
    }
}

@Suite
struct DebugUserTests {
    @Test func matchesIgnoringCaseAndSurroundingWhitespace() {
        let allowList: Set<String> = ["gcca"]

        #expect(AppConfiguration.isDebugUser("gcca", allowList: allowList))
        #expect(AppConfiguration.isDebugUser("  GcCa\n", allowList: allowList))
    }

    @Test func shippedAllowListIncludesGccaAndJosh() {
        #expect(AppConfiguration.isDebugUser("gcca"))
        #expect(AppConfiguration.isDebugUser("  JOSH "))
    }

    @Test func rejectsOtherAndEmptyUsernames() {
        let allowList: Set<String> = ["gcca"]

        #expect(!AppConfiguration.isDebugUser("someone", allowList: allowList))
        #expect(!AppConfiguration.isDebugUser("gcca2", allowList: allowList))
        #expect(!AppConfiguration.isDebugUser("", allowList: allowList))
        #expect(!AppConfiguration.isDebugUser("gcca", allowList: []))
    }
}
