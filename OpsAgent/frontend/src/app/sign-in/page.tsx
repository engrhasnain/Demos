"use client";

/** Choosing who is asking happens on the overview; this address still works. */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function SignIn() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/?choose=1");
  }, [router]);
  return null;
}
