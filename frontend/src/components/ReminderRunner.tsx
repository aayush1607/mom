"use client";

import { useReminderScheduler } from "@/lib/reminders";

/**
 * Mounts the meal-reminder scheduler globally. Renders nothing — its job
 * is just to keep the polling loop alive while any page is open.
 */
export function ReminderRunner() {
  useReminderScheduler();
  return null;
}
