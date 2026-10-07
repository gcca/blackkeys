import Foundation

enum AppConfiguration {
    /// How long cached brand data stays fresh before a refetch is attempted.
    static let brandsCacheTTLSeconds: TimeInterval = 10.5 * 60 // 630

    /// Usernames that get the debug menu (long-press the Home username chip).
    /// A convenience gate, not security: the username is not a secret and
    /// nothing server-side checks it.
    static let debugUsernames: Set<String> = ["gcca", "josh"]

    static func isDebugUser(_ username: String, allowList: Set<String> = debugUsernames) -> Bool {
        let normalized = username.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return allowList.contains { $0.lowercased() == normalized }
    }
}
