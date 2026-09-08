import Foundation

enum AppConfiguration {
    /// How long cached brand data stays fresh before a refetch is attempted.
    static let brandsCacheTTLSeconds: TimeInterval = 10.5 * 60 // 630
}
