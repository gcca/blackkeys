import Foundation
import Testing
@testable import blackkeys

struct ProfileDraftTests {
    @Test func acceptsWellFormedEmailsAndRejectsOthers() {
        for ok in ["a@b.co", " alex@plaza.pe ", "a.b@c.d.pe"] {
            #expect(ProfileDraft(email: ok).isEmailValid, "\(ok)")
        }
        for bad in ["", "alex", "a@b", "@b.co", "a@", "a@@b.co", "a b@c.co", "a@b..co", "a@.co"] {
            #expect(!ProfileDraft(email: bad).isEmailValid, "\(bad)")
        }
    }

    @Test func dniKeepsOnlyUpToEightASCIIDigits() {
        #expect(ProfileDraft.sanitizedDNI("12a3-4 5678 90") == "12345678")
        #expect(ProfileDraft.sanitizedDNI("٣٤") == "")
    }

    @Test func dniIsOptionalButExactlyEightDigitsWhenPresent() {
        #expect(ProfileDraft(dni: "").isDNIValid)
        #expect(ProfileDraft(dni: "12345678").isDNIValid)
        #expect(!ProfileDraft(dni: "1234567").isDNIValid)
        #expect(!ProfileDraft(dni: "1234567a").isDNIValid)
    }

    @Test func aFutureBirthdayIsRejected() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        #expect(ProfileDraft(birthday: nil).isBirthdayValid(now: now))
        #expect(ProfileDraft(birthday: now).isBirthdayValid(now: now))
        #expect(!ProfileDraft(birthday: now.addingTimeInterval(1)).isBirthdayValid(now: now))
    }

    @Test func isValidNeedsAValidEmailDNIAndBirthday() {
        #expect(ProfileDraft(email: "a@b.co", dni: "12345678").isValid())
        #expect(!ProfileDraft(email: "", dni: "12345678").isValid())
        #expect(!ProfileDraft(email: "a@b.co", dni: "123").isValid())
    }
}
