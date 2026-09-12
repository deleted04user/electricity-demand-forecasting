export default function StatsTable({ title, stats, unit }) {
  const rows = [
    ["Mean", stats.mean], ["Median", stats.median], ["Std Dev", stats.std],
    ["Min", stats.min], ["Max", stats.max], ["Q1", stats.q1], ["Q3", stats.q3],
  ];
  return (
    <div className="card">
      <div className="section-title">{title}</div>
      <table>
        <tbody>
          {rows.map(([label, val]) => (
            <tr key={label}><td>{label}</td><td>{val} {unit}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
