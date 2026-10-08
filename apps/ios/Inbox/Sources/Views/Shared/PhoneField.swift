import SwiftUI

/// A phone input the way the web has it: a country with its flag and dial code,
/// then the national number. The bound value is the full digits-only number.
struct PhoneField: View {
    @Binding var phone: String
    var disabled = false
    var accessibilityLabel: String? = nil
    @Environment(\.accent) private var accent
    @State private var iso: String
    @State private var national: String
    @State private var picking = false

    init(phone: Binding<String>, disabled: Bool = false, accessibilityLabel: String? = nil) {
        _phone = phone
        self.disabled = disabled
        self.accessibilityLabel = accessibilityLabel
        let parts = DialCodes.split(phone.wrappedValue)
        _iso = State(initialValue: parts?.iso ?? DialCodes.defaultCountry)
        _national = State(initialValue: parts?.national ?? phone.wrappedValue.filter(\.isNumber))
    }

    var body: some View {
        HStack(spacing: 0) {
            Button { picking = true } label: {
                HStack(spacing: 4) {
                    Text(DialCodes.flag(iso)).font(.title3)
                    Image(systemName: "chevron.down").font(.system(size: 10, weight: .semibold)).foregroundStyle(accent.palette.muted)
                }
                .padding(.horizontal, 12)
                .frame(minHeight: 48)
            }
            .disabled(disabled)
            .accessibilityLabel(DialCodes.name(iso))
            Rectangle().fill(accent.palette.line).frame(width: 0.5, height: 28)
            Text("+\(DialCodes.dialCode(iso))").foregroundStyle(accent.palette.muted).padding(.leading, 12)
            TextField("", text: $national)
                .keyboardType(.phonePad)
                .textContentType(.telephoneNumber)
                .foregroundStyle(accent.palette.ink)
                .padding(.horizontal, 8)
                .frame(minHeight: 48)
                .disabled(disabled)
                .accessibilityLabel(accessibilityLabel ?? "")
        }
        .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
        .onChange(of: national) { _, _ in compose() }
        .onChange(of: iso) { _, _ in compose() }
        .sheet(isPresented: $picking) { CountryPicker(selected: $iso) }
    }

    private func compose() {
        let digits = national.filter(\.isNumber)
        if digits != national { national = digits }
        phone = digits.isEmpty ? "" : DialCodes.dialCode(iso) + digits
    }
}

/// Every country with its flag and dial code, filtered as you type.
struct CountryPicker: View {
    @Binding var selected: String
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accent) private var accent
    @State private var query = ""

    private var rows: [DialCodes.Country] {
        let all = DialCodes.sortedByName
        let needle = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !needle.isEmpty else { return all }
        return all.filter { $0.name.lowercased().contains(needle) || $0.code.hasPrefix(needle.replacingOccurrences(of: "+", with: "")) || $0.iso.lowercased() == needle }
    }

    var body: some View {
        NavigationStack {
            List(rows) { country in
                Button {
                    selected = country.iso
                    dismiss()
                } label: {
                    HStack(spacing: 12) {
                        Text(country.flag).font(.title3)
                        Text(country.name).foregroundStyle(accent.palette.ink)
                        Spacer()
                        Text("+\(country.code)").foregroundStyle(accent.palette.muted)
                        if country.iso == selected { Image(systemName: "checkmark").foregroundStyle(accent.color) }
                    }
                }
            }
            .listStyle(.plain)
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: { Image(systemName: "xmark") }.accessibilityLabel(ChatStrings.current.close)
                }
            }
        }
        .tint(accent.color)
        .presentationDetents([.large])
    }
}
