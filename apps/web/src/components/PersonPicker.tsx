import { useMe, usePeople } from "../hooks";

/** Choose a colleague (internal users, not yourself). */
export default function PersonPicker({ value, onChange, label = "Who", placeholder = "Choose who…", className = "input" }: {
  value: string; onChange: (userId: string) => void; label?: string; placeholder?: string; className?: string;
}) {
  const people = usePeople();
  const me = useMe();
  return (
    <select className={className} value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      <option value="">{placeholder}</option>
      {people.data?.filter((p) => p.user_id !== me.data?.user_id).map((p) => (
        <option key={p.user_id} value={p.user_id}>{p.name} · {p.email}</option>
      ))}
    </select>
  );
}
