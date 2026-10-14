"use client";

import { ChatSurface } from "@/components/chat/chat-surface";

/** The customer's window on the website. No sign-in: the chat is the front door. */
export default function WebChatPage() {
  return <ChatSurface channel="web" />;
}
