//
//  ContentView.swift
//  blackkeys
//
//  Created by gcca on 20/09/26.
//

import SwiftUI

struct ContentView: View {
    @State private var session: AuthSession?
    @State private var isShowingSplash = false

    var body: some View {
        if let session {
            if isShowingSplash {
                SplashView {
                    isShowingSplash = false
                }
            } else {
                HomeView(session: session)
            }
        } else {
            SignInView { newSession in
                session = newSession
                isShowingSplash = true
            }
        }
    }
}

#Preview {
    ContentView()
}
