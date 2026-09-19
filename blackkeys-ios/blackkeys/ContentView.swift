//
//  ContentView.swift
//  blackkeys
//
//  Created by gcca on 20/09/26.
//

import SwiftUI

struct ContentView: View {
    @State private var session: AuthSession?

    var body: some View {
        if let session {
            HomeView(session: session)
        } else {
            SignInView { session = $0 }
        }
    }
}

#Preview {
    ContentView()
}
