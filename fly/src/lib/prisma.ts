import { PrismaClient } from "@generated/prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import process from "node:process";

const adapter = new PrismaBetterSqlite3(
    { url: process.env.DATABASE_URL },
    { timestampFormat: "unixepoch-ms" },
);
export const prisma = new PrismaClient({ adapter });
