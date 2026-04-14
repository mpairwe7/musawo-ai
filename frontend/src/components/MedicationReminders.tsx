"use client";

import { memo, useCallback, useEffect, useState } from "react";
import {
  getReminders,
  saveReminder,
  deleteReminder,
} from "@/lib/offlineDb";

interface Reminder {
  id: string;
  name: string;
  dosage: string;
  frequency: string;
  nextDue: string;
  createdAt: number;
}

export default memo(function MedicationReminders() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [dosage, setDosage] = useState("");
  const [frequency, setFrequency] = useState("daily");

  // Load reminders from IndexedDB
  useEffect(() => {
    getReminders().then((r) => setReminders(r as Reminder[]));
  }, []);

  const handleAdd = useCallback(async () => {
    if (!name.trim()) return;
    const reminder: Reminder = {
      id: `rem-${Date.now()}`,
      name: name.trim(),
      dosage: dosage.trim(),
      frequency,
      nextDue: new Date(Date.now() + 86400000).toISOString(),
      createdAt: Date.now(),
    };
    await saveReminder(reminder);
    setReminders((prev) => [...prev, reminder]);
    setName("");
    setDosage("");
    setShowForm(false);
  }, [name, dosage, frequency]);

  const handleDelete = useCallback(async (id: string) => {
    await deleteReminder(id);
    setReminders((prev) => prev.filter((r) => r.id !== id));
  }, []);

  if (reminders.length === 0 && !showForm) {
    return (
      <div className="reminders-empty">
        <button
          className="chip"
          onClick={() => setShowForm(true)}
          aria-label="Add medication reminder"
        >
          + Add medication reminder
        </button>
      </div>
    );
  }

  return (
    <div className="reminders-panel">
      <div className="reminders-header">
        <h3>Medication Reminders</h3>
        <button
          className="reminders-add-btn"
          onClick={() => setShowForm((v) => !v)}
          aria-label={showForm ? "Cancel" : "Add reminder"}
        >
          {showForm ? "Cancel" : "+ Add"}
        </button>
      </div>

      {showForm && (
        <div className="reminder-form">
          <input
            className="reminder-input"
            placeholder="Medicine name (e.g. Panadol)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
          />
          <input
            className="reminder-input"
            placeholder="Dosage (e.g. 2 tablets)"
            value={dosage}
            onChange={(e) => setDosage(e.target.value)}
            maxLength={100}
          />
          <select
            className="select-input"
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
          >
            <option value="daily">Once daily</option>
            <option value="twice">Twice daily</option>
            <option value="thrice">Three times daily</option>
            <option value="weekly">Once weekly</option>
          </select>
          <button className="reminder-save-btn" onClick={handleAdd} disabled={!name.trim()}>
            Save Reminder
          </button>
        </div>
      )}

      <ul className="reminder-list">
        {reminders.map((r) => (
          <li key={r.id} className="reminder-item">
            <div>
              <strong>{r.name}</strong>
              {r.dosage && <span className="reminder-dosage"> &mdash; {r.dosage}</span>}
              <p className="reminder-freq">{r.frequency}</p>
            </div>
            <button
              className="reminder-delete"
              onClick={() => handleDelete(r.id)}
              aria-label={`Delete ${r.name} reminder`}
            >
              &times;
            </button>
          </li>
        ))}
      </ul>

      <p className="reminder-note">
        These reminders are stored on your device only. Follow what your health worker prescribed.
      </p>
    </div>
  );
});
