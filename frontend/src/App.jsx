import { Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import GuestOnly from "./components/GuestOnly";
import Landing from "./pages/Landing";
import About from "./pages/About";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Onboarding from "./pages/Onboarding";
import UploadPrescription from "./pages/UploadPrescription";
import PrescriptionHistory from "./pages/PrescriptionHistory";
import PrescriptionReport from "./pages/PrescriptionReport";
import MedicineSearch from "./pages/MedicineSearch";
import ScanMedicine from "./pages/ScanMedicine";
import StoreFinder from "./pages/StoreFinder";
import Profile from "./pages/Profile";

const guarded = (element) => <ProtectedRoute>{element}</ProtectedRoute>;

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/about" element={<About />} />
        <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
        <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
        <Route path="/dashboard" element={guarded(<Dashboard />)} />
        <Route path="/onboarding" element={guarded(<Onboarding />)} />
        <Route path="/upload" element={guarded(<UploadPrescription />)} />
        <Route path="/search" element={guarded(<MedicineSearch />)} />
        <Route path="/scan" element={guarded(<ScanMedicine />)} />
        <Route path="/stores" element={guarded(<StoreFinder />)} />
        <Route path="/prescriptions" element={guarded(<PrescriptionHistory />)} />
        <Route path="/prescriptions/:id" element={guarded(<PrescriptionReport />)} />
        <Route path="/profile" element={guarded(<Profile />)} />
        <Route path="*" element={<Landing />} />
      </Routes>
    </AuthProvider>
  );
}
