import Foundation
import Testing
@testable import blackkeys

@Suite
struct BrandDetailFormattingTests {
    private static func brand(isActive: Bool, stores: [Brand.Store]) -> Brand {
        Brand(
            name: "TEST",
            displayName: "Test",
            description: "",
            isActive: isActive,
            kioskId: 1,
            amenities: [],
            stores: stores,
            tags: []
        )
    }

    @Test func locationAndStatusAreJoinedWithADivider() {
        let brand = Self.brand(isActive: true, stores: [Brand.Store(id: 1, name: "Corredor Mantaro, 2do nivel")])
        #expect(BrandDetailFormatting.subtitle(for: brand) == "Corredor Mantaro, 2do nivel · Abierto")
    }

    @Test func missingLocationFallsBackToStatusOnly() {
        let brand = Self.brand(isActive: false, stores: [])
        #expect(BrandDetailFormatting.subtitle(for: brand) == "Cerrado")
    }
}
