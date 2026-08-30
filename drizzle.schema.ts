// Drizzle schema for Cloudflare D1 — preferred for edge (smaller bundle, native D1)
// Use with: drizzle-orm/d1 + drizzle-kit
// `npm i drizzle-orm @cloudflare/workers-types` + `wrangler d1 create tls-events`

import { sqliteTable, text, integer } from "drizzle-orm/sqlite-core";
import { relations } from "drizzle-orm";

export const events = sqliteTable("events", {
  id: text("id").primaryKey(),
  slug: text("slug").notNull().unique(),
  title: text("title").notNull(),
  description: text("description"),
  category: text("category").notNull(), // GLOBAL | PHILIPPINES | MANILA | DLSU | TLS
  subcategory: text("subcategory"),
  logic: text("logic").notNull(), // fixed | movable_nth | undated | tba_*
  month: integer("month"), // null = undated pool
  day: integer("day"),
  ruleJson: text("rule_json"), // JSON string
  tbaSource: text("tba_source"),
  isTba: integer("is_tba", { mode: "boolean" }).default(false),
  isUndated: integer("is_undated", { mode: "boolean" }).default(false),
  foundedYear: integer("founded_year"),
  foundedDate: text("founded_date"),
  foundedAuthority: text("founded_authority"),
  relevanceTier: text("relevance_tier"),
  typeOfVisual: text("type_of_visual"),
  sourceUrl: text("source_url"),
  notionUrl: text("notion_url"),
  tags: text("tags"), // JSON array
  createdAt: text("created_at").default("datetime('now')"),
  updatedAt: text("updated_at"),
});

export const occurrences = sqliteTable("occurrences", {
  id: text("id").primaryKey(),
  eventId: text("event_id").notNull().references(() => events.id, { onDelete: "cascade" }),
  year: integer("year").notNull(),
  date: text("date").notNull(), // ISO
  isTba: integer("is_tba", { mode: "boolean" }).notNull(),
  isMilestone: integer("is_milestone", { mode: "boolean" }).notNull(),
  anniversary: integer("anniversary"),
  prioScore: integer("prio_score"), // 0-100
});

export const monthlyIssues = sqliteTable("monthly_issues", {
  id: text("id").primaryKey(),
  year: integer("year").notNull(),
  month: integer("month").notNull(),
  status: text("status").notNull().default("draft"),
  version: integer("version").notNull().default(1),
  createdAt: text("created_at").default("datetime('now')"),
  updatedAt: text("updated_at"),
});

export const monthlyPicks = sqliteTable("monthly_picks", {
  id: text("id").primaryKey(),
  issueId: text("issue_id").notNull().references(() => monthlyIssues.id, { onDelete: "cascade" }),
  eventId: text("event_id").notNull().references(() => events.id),
  status: text("status").notNull().default("picked"),
  priority: integer("priority"),
  deadline: text("deadline"),
  artist: text("artist"),
  notes: text("notes"),
  addedBy: text("added_by"),
});

// Relations
export const eventsRelations = relations(events, ({ many }) => ({
  occurrences: many(occurrences),
  picks: many(monthlyPicks),
}));

// helpers
export const prioScore = (anniv: number | null): number => {
  if (anniv == null) return 0;
  if (anniv % 100 === 0) return 100; // centennial
  if (anniv % 50 === 0) return 80;
  if (anniv % 25 === 0) return 60;
  if (anniv % 10 === 0) return 40;
  if (anniv % 5 === 0) return 20;
  return 5; // any other anniversary still > no anniversary
};
