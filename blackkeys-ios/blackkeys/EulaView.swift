import SwiftUI

struct EulaView: View {
    @Binding var hasAcceptedEula: Bool

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Illustrative End User License Agreement")
                    .font(.title2.bold())

                Text("This example agreement is provided for demonstration only. It is not legal advice or production legal language.")
                    .foregroundStyle(.secondary)

                agreementSection(
                    title: "Use of the app",
                    body: "Use Black Keys lawfully and only with accounts and data you are authorized to access."
                )

                agreementSection(
                    title: "Your responsibilities",
                    body: "Keep your sign-in credentials secure and notify the service owner if you believe your account has been used without permission."
                )

                agreementSection(
                    title: "Service availability",
                    body: "The service may change, be interrupted, or be unavailable. No availability or fitness guarantee is made by this illustrative agreement."
                )
            }
            .padding()
        }
        .navigationTitle("End User License Agreement")
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            GlassEffectContainer(spacing: 12) {
                HStack {
                    if !hasAcceptedEula {
                        Button("Accept", action: accept)
                            .buttonStyle(.glassProminent)
                            .accessibilityIdentifier("eulaAcceptButton")
                    }

                    Button("Reject", action: reject)
                        .buttonStyle(.glass)
                        .accessibilityIdentifier("eulaRejectButton")
                }
                .frame(maxWidth: .infinity, alignment: .trailing)
            }
            .padding()
        }
    }

    private func agreementSection(title: String, body: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.headline)
            Text(body)
        }
    }

    private func accept() {
        hasAcceptedEula = true
        dismiss()
    }

    private func reject() {
        hasAcceptedEula = false
        dismiss()
    }
}

private struct EulaViewPreview: View {
    @State private var hasAcceptedEula = false

    var body: some View {
        NavigationStack {
            EulaView(hasAcceptedEula: $hasAcceptedEula)
        }
    }
}

#Preview {
    EulaViewPreview()
}
