import SwiftUI

struct SignInView: View {
    private let authService: AuthService
    private let onSignedIn: (AuthSession) -> Void

    @State private var username = ""
    @State private var password = ""
    @State private var hasAcceptedEula = false
    @State private var errorMessage: String?
    @State private var isSigningIn = false

    init(authService: AuthService = AuthService(), onSignedIn: @escaping (AuthSession) -> Void) {
        self.authService = authService
        self.onSignedIn = onSignedIn
    }

    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(
                    colors: [Color.accentColor.opacity(0.35), Color(.systemBackground)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                VStack(spacing: 24) {
                    Spacer()

                    GlassEffectContainer(spacing: 16) {
                        VStack(spacing: 16) {
                            TextField("Username", text: $username)
                                .textContentType(.username)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .accessibilityIdentifier("usernameTextField")
                                .padding(.horizontal, 16)
                                .padding(.vertical, 12)
                                .glassEffect(in: .capsule)

                            SecureField("Password", text: $password)
                                .textContentType(.password)
                                .accessibilityIdentifier("passwordSecureField")
                                .onSubmit(signIn)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 12)
                                .glassEffect(in: .capsule)

                            if let errorMessage {
                                Text(errorMessage)
                                    .foregroundStyle(.red)
                                    .accessibilityIdentifier("signInError")
                            }

                            Button(action: signIn) {
                                if isSigningIn {
                                    ProgressView()
                                        .frame(maxWidth: .infinity)
                                } else {
                                    Text("Sign In")
                                        .frame(maxWidth: .infinity)
                                }
                            }
                            .buttonStyle(.glass)
                            .disabled(!canSubmit || isSigningIn)
                            .accessibilityIdentifier("signInButton")
                        }
                    }
                    .padding(.horizontal)

                    Spacer()

                    NavigationLink {
                        EulaView(hasAcceptedEula: $hasAcceptedEula)
                    } label: {
                        HStack(spacing: 8) {
                            if !hasAcceptedEula {
                                Image(systemName: "square")
                                    .accessibilityIdentifier("eulaCheckbox")
                            }

                            Text("End User License Agreement")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .accessibilityIdentifier("eulaLink")
                    .padding()
                }
            }
            .navigationTitle("Black Keys")
        }
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
