import Foundation

/// The editable profile fields and their validation. Pure value type so the
/// rules are testable without any UI.
struct ProfileDraft: Equatable, Sendable {
    static let dniLength = 8

    var email = ""
    var birthday: Date?
    var dni = ""

    /// Digits only, at most `dniLength`; what a DNI field should hold as typed.
    static func sanitizedDNI(_ text: String) -> String {
        String(text.filter { $0.isASCII && $0.isNumber }.prefix(dniLength))
    }

    var trimmedEmail: String {
        email.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Required: one `@` with text on both sides and a dot inside the domain.
    var isEmailValid: Bool {
        let parts = trimmedEmail.split(separator: "@", omittingEmptySubsequences: false)
        guard parts.count == 2, !parts[0].isEmpty, !parts[1].isEmpty,
              !trimmedEmail.contains(where: \.isWhitespace) else { return false }
        let domain = parts[1].split(separator: ".", omittingEmptySubsequences: false)
        return domain.count >= 2 && domain.allSatisfy { !$0.isEmpty }
    }

    /// Optional, but when present it must be exactly 8 digits (Peruvian DNI).
    var isDNIValid: Bool {
        dni.isEmpty || (dni.count == Self.dniLength && dni == Self.sanitizedDNI(dni))
    }

    func isBirthdayValid(now: Date = .now) -> Bool {
        birthday.map { $0 <= now } ?? true
    }

    func isValid(now: Date = .now) -> Bool {
        isEmailValid && isDNIValid && isBirthdayValid(now: now)
    }
}
