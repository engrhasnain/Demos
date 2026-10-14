import type { MetadataRoute } from "next";

/** FrontDesk installs as an app on a phone: the customer chat is the front door. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FrontDesk - Hengtai Industrial Supply",
    short_name: "FrontDesk",
    description: "Ask about an order, a return or a technician visit, any time.",
    start_url: "/chat",
    scope: "/",
    display: "standalone",
    background_color: "#fff8f4",
    theme_color: "#ff6b4a",
    icons: [
      { src: "/frontdesk-icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/frontdesk-icon-maskable.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" },
    ],
  };
}
