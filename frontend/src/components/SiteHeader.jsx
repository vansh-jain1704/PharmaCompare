import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { ChevronDown, History, LayoutDashboard, LogOut, Pill, ScanSearch, User } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import BrandMark from "./ui/BrandMark";
import ThemeToggle from "./ui/ThemeToggle";

const NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/upload", label: "Analyze" },
  { to: "/search", label: "Medicines" },
  { to: "/prescriptions", label: "History" },
  { to: "/about", label: "About" },
];

const TABS = [
  { to: "/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/upload", label: "Analyze", icon: ScanSearch },
  { to: "/search", label: "Medicines", icon: Pill },
  { to: "/prescriptions", label: "History", icon: History },
  { to: "/profile", label: "Profile", icon: User },
];

const navClass = ({ isActive }) => (isActive ? "is-active" : "");

/**
 * Fixed header on every page. Signed in: main links, theme toggle and a user
 * menu (Profile, Log out), plus a bottom tab bar on small screens. Signed
 * out: About, theme toggle, Login and Get started.
 */
export default function SiteHeader() {
  const { user, status, logout } = useAuth();
  const navigate = useNavigate();
  const isAuthed = status === "authenticated";
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDown = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  function handleLogout() {
    setMenuOpen(false);
    logout();
    navigate("/login");
  }

  return (
    <>
      <header className={`topbar ${isAuthed ? "" : "is-guest"}`}>
        <div className="topbar-inner">
          <Link to={isAuthed ? "/dashboard" : "/"} className="brand" aria-label="PharmaCompare home">
            <BrandMark />
            <span className="brand-text">PharmaCompare</span>
          </Link>

          <nav className="nav" aria-label="Main">
            {(isAuthed ? NAV : NAV.filter((l) => l.to === "/about")).map((link) => (
              <NavLink key={link.to} to={link.to} className={navClass}>{link.label}</NavLink>
            ))}
          </nav>

          <div className="topbar-actions">
            <ThemeToggle />
            {isAuthed ? (
              <div className="user-menu" ref={menuRef}>
                <button
                  type="button" className="user-trigger" aria-haspopup="menu" aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((o) => !o)}
                >
                  <span className="avatar">{(user?.name || "?").charAt(0).toUpperCase()}</span>
                  <span className="user-name">{user?.name}</span>
                  <ChevronDown size={14} className="user-chevron" aria-hidden="true" />
                </button>
                {menuOpen && (
                  <div className="menu" role="menu">
                    <div className="menu-head">
                      <strong>{user?.name}</strong>
                      <span>{user?.email}</span>
                    </div>
                    <Link to="/profile" className="menu-item" role="menuitem" onClick={() => setMenuOpen(false)}>
                      <User size={15} /> Profile &amp; health preferences
                    </Link>
                    <button type="button" className="menu-item" role="menuitem" onClick={handleLogout}>
                      <LogOut size={15} /> Log out
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <>
                <Link to="/login" className="btn btn-ghost btn-sm">Login</Link>
                <Link to="/register" className="btn btn-primary btn-sm">Get started</Link>
              </>
            )}
          </div>
        </div>
      </header>
      <div className="topbar-spacer" aria-hidden="true" />

      {isAuthed && (
        <nav className="tabbar" aria-label="Primary">
          {TABS.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={navClass}>
              <Icon size={20} />
              {label}
            </NavLink>
          ))}
        </nav>
      )}
    </>
  );
}
