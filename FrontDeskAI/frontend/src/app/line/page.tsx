"use client";

import { ChatSurface } from "@/components/chat/chat-surface";

/** The LINE channel: the same engine the LINE webhook calls, in a phone. */
export default function LineChatPage() {
  return <ChatSurface channel="line" />;
}
