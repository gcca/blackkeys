import SwiftUI

private enum SignInField: Hashable {
    case username
    case password
}

struct SignInView: View {
    private let authService: AuthService
    private let onSignedIn: (AuthSession) -> Void

    @State private var username = ""
    @State private var password = ""
    @State private var isUsernameConfirmed = false
    @State private var hasAcceptedEula = false
    @State private var errorMessage: String?
    @State private var isSigningIn = false
    @FocusState private var focusedField: SignInField?

    init(authService: AuthService = AuthService(), onSignedIn: @escaping (AuthSession) -> Void) {
        self.authService = authService
        self.onSignedIn = onSignedIn
    }

    private var backgroundVideoURL: URL {
        Bundle.main.url(forResource: "SignInBackground", withExtension: "mp4")!
    }

    var body: some View {
        NavigationStack {
            ZStack {
                backgroundVideo

                VStack {
                    HStack {
                        Spacer()
                        wordmarkBlock
                    }
                    .padding(.top, 20)
                    .padding(.horizontal, 20)

                    Spacer()
                }
            }
            .safeAreaInset(edge: .bottom) {
                bottomFormCard
            }
            .navigationTitle("Black Keys")
            .toolbar(.hidden, for: .navigationBar)
        }
    }

    /// Both layers use a bare `.ignoresSafeArea()` (all regions, all edges)
    /// rather than `.ignoresSafeArea(.container, ...)`: `.container` excludes
    /// the `.keyboard` region, so the raised keyboard would inset this ZStack
    /// from the bottom and shrink the video and its gradient with it, leaving
    /// blank window background around `bottomFormCard`. Only that card — a
    /// bottom `safeAreaInset` — should track the keyboard.
    private var backgroundVideo: some View {
        ZStack {
            LoopingVideoView(url: backgroundVideoURL)
                .ignoresSafeArea()

            LinearGradient(
                colors: [
                    Color.black.opacity(0.65),
                    Color.black.opacity(0.1),
                    Color.black.opacity(0.15),
                    Color.black.opacity(0.75)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        }
        .contentShape(Rectangle())
        .onTapGesture {
            focusedField = nil
        }
    }

    private var wordmarkBlock: some View {
        VStack(alignment: .trailing, spacing: 4) {
            Text("PLAZA SAN MIGUEL")
                .font(.title2.weight(.bold))
                .tracking(2)
                .minimumScaleFactor(0.8)
                .foregroundStyle(.white)

            Text("Black Keys")
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.85))
        }
        .multilineTextAlignment(.trailing)
        .accessibilityElement(children: .combine)
    }

    private var bottomFormCard: some View {
        VStack(spacing: 12) {
            usernameField
            if isUsernameConfirmed {
                passwordField
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .accessibilityIdentifier("signInError")
            }

            NavigationLink {
                EulaView(hasAcceptedEula: $hasAcceptedEula)
            } label: {
                HStack(spacing: 6) {
                    if !hasAcceptedEula {
                        Image(systemName: "square")
                            .accessibilityIdentifier("eulaCheckbox")
                    }

                    Text("End User License Agreement")
                        .font(.footnote)
                }
                .frame(maxWidth: .infinity)
                .foregroundStyle(.white.opacity(0.9))
            }
            .accessibilityIdentifier("eulaLink")
        }
        .padding(.horizontal)
        .padding(.bottom, 8)
    }

    /// Both `usernameField`'s label/field swap and `passwordField`'s
    /// insertion happen via plain `if`/`else`, not opacity/height toggles —
    /// simpler, and each field renders its own independent glass capsule
    /// rather than sharing one `GlassEffectContainer` (that container is for
    /// shapes that should visually merge, which these two never should).
    /// `confirmUsername()` flips `isUsernameConfirmed` and reassigns
    /// `focusedField` to `.password` in the same state update, so focus
    /// moves directly onto the newly-inserted `passwordField` rather than
    /// passing through `nil` — no separate hide/show keyboard animation.
    @ViewBuilder
    private var usernameField: some View {
        if isUsernameConfirmed {
            confirmedUsernameLabel
        } else {
            TextField("Username", text: $username)
                .textContentType(.username)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .submitLabel(.next)
                .focused($focusedField, equals: .username)
                .onSubmit(confirmUsername)
                .accessibilityIdentifier("usernameTextField")
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .glassEffect(in: .capsule)
        }
    }

    /// `.contentShape(Rectangle())` is required here: `.buttonStyle(.plain)`
    /// only makes the label's opaque content tappable by default, so the
    /// `Spacer()`'s expanded region between the text and pencil icon would
    /// otherwise swallow taps that land on it (this button's whole frame
    /// counts as tappable, matching its visible capsule).
    private var confirmedUsernameLabel: some View {
        Button {
            withAnimation(.snappy) {
                isUsernameConfirmed = false
            }
            focusedField = .username
        } label: {
            HStack {
                Text(username)
                Spacer()
                Image(systemName: "pencil")
                    .foregroundStyle(.secondary)
            }
            .foregroundStyle(.primary)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .glassEffect(in: .capsule)
        .accessibilityIdentifier("usernameConfirmedLabel")
    }

    private var passwordField: some View {
        SecureField("Password", text: $password)
            .textContentType(.password)
            .submitLabel(.go)
            .focused($focusedField, equals: .password)
            .accessibilityIdentifier("passwordSecureField")
            .onSubmit(signIn)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .glassEffect(in: .capsule)
            .disabled(isSigningIn)
            .overlay(alignment: .trailing) {
                if isSigningIn {
                    ProgressView()
                        .padding(.trailing, 16)
                }
            }
    }

    private func confirmUsername() {
        let trimmed = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        username = trimmed
        withAnimation(.snappy) {
            isUsernameConfirmed = true
        }
        focusedField = .password
    }

    private var canSubmit: Bool {
        !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !password.isEmpty
    }

    private func signIn() {
        guard canSubmit, !isSigningIn else {
            return
        }

        let submittedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        let submittedPassword = password
        errorMessage = nil
        isSigningIn = true

        Task {
            defer { isSigningIn = false }

            do {
                let session = try await authService.signIn(
                    username: submittedUsername,
                    password: submittedPassword
                )
                onSignedIn(session)
            } catch let error as LocalizedError {
                errorMessage = error.errorDescription ?? "Unable to sign in."
            } catch {
                errorMessage = "Unable to sign in."
            }
        }
    }
}

#Preview {
    SignInView { _ in }
}
