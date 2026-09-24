import { redirect } from "next/navigation";

// OAuth and invite links land on "/" with ?drive= / ?invite=; keep the query.
export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    for (const item of [value ?? []].flat()) query.append(key, item);
  }
  const qs = query.toString();
  redirect(qs ? `/stacks?${qs}` : "/stacks");
}
