import { initializeApp, getApps, getApp, FirebaseApp } from "firebase/app";
import { getFirestore, Firestore } from "firebase/firestore";
import { getAuth, Auth } from "firebase/auth";

const defaultConfig = {
  apiKey: "demo-api-key",
  authDomain: "project-alpha.firebaseapp.com",
  projectId: "project-alpha",
  storageBucket: "project-alpha.appspot.com",
  messagingSenderId: "000000000000",
  appId: "1:000000000000:web:0000000000000000000000"
};

const app: FirebaseApp = getApps().length === 0 ? initializeApp(defaultConfig) : getApp();

export const db: Firestore = getFirestore(app);
export const auth: Auth = getAuth(app);

export default app;

