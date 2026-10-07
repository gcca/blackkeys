import SwiftUI

/// Profile form opened from the username in `HomeView`'s header. UI only for
/// now: `onSave` is where a profile service call plugs in later; nothing is
/// loaded from or stored anywhere yet.
struct ProfileView: View {
    let username: String
    let initial: ProfileDraft
    let onSave: (ProfileDraft) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var draft: ProfileDraft
    @FocusState private var focusedField: Field?

    private enum Field { case email, dni }

    init(username: String, initial: ProfileDraft = ProfileDraft(), onSave: @escaping (ProfileDraft) -> Void = { _ in }) {
        self.username = username
        self.initial = initial
        self.onSave = onSave
        _draft = State(initialValue: initial)
    }

    private var canSave: Bool {
        draft != initial && draft.isValid()
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Account") {
                    LabeledContent("Username", value: username)
                        .accessibilityElement(children: .combine)
                        .accessibilityIdentifier("profileUsernameRow")
                }

                Section("Personal data") {
                    TextField("Email", text: $draft.email)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($focusedField, equals: .email)
                        .accessibilityIdentifier("profileEmailField")

                    if !draft.email.isEmpty && !draft.isEmailValid {
                        validationMessage("Enter a valid email address.")
                    }

                    DatePicker(
                        "Birthday",
                        selection: birthdayBinding,
                        in: ...Date.now,
                        displayedComponents: .date
                    )
                    .accessibilityIdentifier("profileBirthdayPicker")

                    TextField("DNI (8 digits)", text: dniBinding)
                        .keyboardType(.numberPad)
                        .focused($focusedField, equals: .dni)
                        .accessibilityIdentifier("profileDniField")

                    if !draft.isDNIValid {
                        validationMessage("The DNI has exactly 8 digits.")
                    }
                }
            }
            .navigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .accessibilityIdentifier("profileCancelButton")
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onSave(draft)
                        dismiss()
                    }
                    .disabled(!canSave)
                    .accessibilityIdentifier("profileSaveButton")
                }
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .accessibilityIdentifier("profileView")
    }

    /// `DatePicker` needs a value; an untouched birthday stays nil, and
    /// choosing a date sets it.
    private var birthdayBinding: Binding<Date> {
        Binding(
            get: {
                draft.birthday
                    ?? Calendar.current.date(byAdding: .year, value: -18, to: .now)
                    ?? .now
            },
            set: { draft.birthday = $0 }
        )
    }

    private var dniBinding: Binding<String> {
        Binding(
            get: { draft.dni },
            set: { draft.dni = ProfileDraft.sanitizedDNI($0) }
        )
    }

    private func validationMessage(_ text: String) -> some View {
        Text(text)
            .font(.footnote)
            .foregroundStyle(.red)
    }
}

#Preview {
    ProfileView(username: "alex")
}
