import { groupSourceNotices, noticePeriodSummary } from "@/lib/sourceNotices";

export default function SourceNoticeGroups({ notices = [], label = "Source and compatibility notices" }) {
  if (!notices.length) return null;
  const groups = groupSourceNotices(notices);
  return (
    <details className="research-source-notices">
      <summary>{label}: {groups.length} issue type{groups.length === 1 ? "" : "s"} · {notices.length} notice{notices.length === 1 ? "" : "s"}</summary>
      <ul className="research-notice-groups">
        {groups.map((group) => <li key={group.key}>
          <strong>{group.title}</strong> <span className="research-caption">· {group.notices.length} notice{group.notices.length === 1 ? "" : "s"}</span>
          {group.periods.length > 0 && <p className="research-caption">Affected periods: {noticePeriodSummary(group.periods)}</p>}
          {group.fields.length > 0 && <p className="research-caption">Affected fields: {group.fields.join(", ")}</p>}
          <p>{group.message}</p>
          <details className="research-original-diagnostics">
            <summary>View {group.notices.length} original diagnostic{group.notices.length === 1 ? "" : "s"}</summary>
            {group.notices.map((notice, index) => <pre key={index}>{typeof notice === "string" ? notice : JSON.stringify(notice, null, 2)}</pre>)}
          </details>
        </li>)}
      </ul>
    </details>
  );
}
