import Foundation

/// `Brand` has no floor/hours fields — `Brand.Store.name` is a human-readable
/// location string (e.g. "Corredor Mantaro, 2do nivel"), not a product name.
/// This joins that location with a plain open/closed status word.
enum BrandDetailFormatting {
    static func subtitle(for brand: Brand) -> String {
        let status = brand.isActive ? "Abierto" : "Cerrado"
        guard let location = brand.stores.first?.name, !location.isEmpty else {
            return status
        }
        return "\(location) · \(status)"
    }
}
