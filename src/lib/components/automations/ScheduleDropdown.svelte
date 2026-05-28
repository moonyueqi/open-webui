<script lang="ts">
	import type i18nType from '$lib/i18n';
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Dropdown from '$lib/components/automations/_Dropdown.svelte';

	const i18n: typeof i18nType = getContext('i18n');

	export let frequency = 'DAILY';
	export let interval = 1;
	export let hour = 9;
	export let minute = 0;
	// Multiple times per day, format "HH:MM". Used when frequency === 'DAILY'.
	// Kept in sync with hour/minute (first entry).
	export let dailyTimes: string[] = ['09:00'];
	export let selectedDays: string[] = [];
	export let monthDay = 1;
	export let onceDate = '';
	export let onceTime = '09:00';
	export let customRrule = '';

	export let side: 'top' | 'bottom' = 'top';
	export let align: 'start' | 'end' = 'start';

	/** Optional callback when any value changes */
	export let onChange: () => void = () => {};

	let showDropdown = false;

	$: FREQUENCIES = [
		{ key: 'ONCE', label: $i18n.t('Once') },
		{ key: 'HOURLY', label: $i18n.t('Hourly') },
		{ key: 'DAILY', label: $i18n.t('Daily') },
		{ key: 'WEEKLY', label: $i18n.t('Weekly') },
		{ key: 'MONTHLY', label: $i18n.t('Monthly') }
	];

	$: DAYS = [
		{ key: 'MO', label: $i18n.t('Mo', { context: 'day_of_week' }) },
		{ key: 'TU', label: $i18n.t('Tu', { context: 'day_of_week' }) },
		{ key: 'WE', label: $i18n.t('We', { context: 'day_of_week' }) },
		{ key: 'TH', label: $i18n.t('Th', { context: 'day_of_week' }) },
		{ key: 'FR', label: $i18n.t('Fr', { context: 'day_of_week' }) },
		{ key: 'SA', label: $i18n.t('Sa', { context: 'day_of_week' }) },
		{ key: 'SU', label: $i18n.t('Su', { context: 'day_of_week' }) }
	];

	let lastVisualFrequency = 'DAILY';
	let prevFrequency = 'DAILY';

	$: if (frequency !== 'CUSTOM') {
		lastVisualFrequency = frequency;
	}

	$: if (frequency === 'ONCE' && !onceDate) {
		const soon = new Date(Date.now() + 5 * 60_000);
		onceDate = soon.toISOString().split('T')[0];
		onceTime = `${String(soon.getHours()).padStart(2, '0')}:${String(soon.getMinutes()).padStart(2, '0')}`;
	}

	// Keep dailyTimes[0] in sync with hour/minute so that switching between DAILY
	// (which supports multi-times) and WEEKLY/MONTHLY (single time) works smoothly.
	$: if (dailyTimes.length === 0) {
		dailyTimes = [`${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`];
	}

	// Track which times appear more than once so we can highlight them in the UI.
	$: duplicateTimeSet = (() => {
		const seen = new Map<string, number>();
		for (const t of dailyTimes) {
			seen.set(t, (seen.get(t) ?? 0) + 1);
		}
		const dup = new Set<string>();
		for (const [t, c] of seen) {
			if (c > 1) dup.add(t);
		}
		return dup;
	})();

	$: hasDuplicateTimes = duplicateTimeSet.size > 0;

	$: {
		if (frequency === 'CUSTOM' && prevFrequency !== 'CUSTOM') {
			customRrule = buildVisualRrule();
		}
		prevFrequency = frequency;
	}

	const dedupeSortedTimes = (times: string[]): string[] => {
		const valid = times.filter((t) => /^\d{2}:\d{2}$/.test(t));
		const set = Array.from(new Set(valid));
		set.sort();
		return set.length ? set : ['09:00'];
	};

	const buildDailyRrule = (times: string[], intervalVal: number): string => {
		const list = dedupeSortedTimes(times);
		const lines = list.map((t) => {
			const [h, m] = t.split(':').map(Number);
			const parts = [`FREQ=DAILY`];
			if (intervalVal > 1) parts.push(`INTERVAL=${intervalVal}`);
			parts.push(`BYHOUR=${h}`);
			parts.push(`BYMINUTE=${m}`);
			return `RRULE:${parts.join(';')}`;
		});
		return lines.join('\n');
	};

	const buildVisualRrule = (): string => {
		if (lastVisualFrequency === 'ONCE') {
			const dt = onceDate.replace(/-/g, '') + 'T' + onceTime.replace(/:/g, '') + '00';
			return `DTSTART:${dt}\nRRULE:FREQ=DAILY;COUNT=1`;
		}
		if (lastVisualFrequency === 'DAILY') {
			return buildDailyRrule(dailyTimes, interval);
		}
		let parts = [`FREQ=${lastVisualFrequency}`];
		if (interval > 1) parts.push(`INTERVAL=${interval}`);
		if (lastVisualFrequency === 'WEEKLY' && selectedDays.length) {
			parts.push(`BYDAY=${selectedDays.join(',')}`);
		}
		if (lastVisualFrequency === 'MONTHLY') {
			parts.push(`BYMONTHDAY=${monthDay}`);
		}
		if (['WEEKLY', 'MONTHLY'].includes(lastVisualFrequency)) {
			parts.push(`BYHOUR=${hour}`);
		}
		parts.push(`BYMINUTE=${minute}`);
		return `RRULE:${parts.join(';')}`;
	};

	export const buildRrule = (): string => {
		if (frequency === 'CUSTOM') return customRrule;
		if (frequency === 'ONCE') {
			const dt = onceDate.replace(/-/g, '') + 'T' + onceTime.replace(/:/g, '') + '00';
			return `DTSTART:${dt}\nRRULE:FREQ=DAILY;COUNT=1`;
		}
		if (frequency === 'DAILY') {
			return buildDailyRrule(dailyTimes, interval);
		}
		let parts = [`FREQ=${frequency}`];
		if (interval > 1) parts.push(`INTERVAL=${interval}`);
		if (frequency === 'WEEKLY' && selectedDays.length) {
			parts.push(`BYDAY=${selectedDays.join(',')}`);
		}
		if (frequency === 'MONTHLY') {
			parts.push(`BYMONTHDAY=${monthDay}`);
		}
		if (['WEEKLY', 'MONTHLY'].includes(frequency)) {
			parts.push(`BYHOUR=${hour}`);
		}
		parts.push(`BYMINUTE=${minute}`);
		return `RRULE:${parts.join(';')}`;
	};

	const parseSingleRrule = (line: string): Record<string, string> => {
		const parts: Record<string, string> = {};
		line.replace('RRULE:', '')
			.split(';')
			.forEach((p) => {
				const [k, v] = p.split('=');
				if (k && v) parts[k] = v;
			});
		return parts;
	};

	export const parseRrule = (s: string) => {
		// Detect ONCE (COUNT=1 with DTSTART)
		if (s.includes('COUNT=1')) {
			frequency = 'ONCE';
			const match = s.match(/DTSTART:(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})/);
			if (match) {
				onceDate = `${match[1]}-${match[2]}-${match[3]}`;
				onceTime = `${match[4]}:${match[5]}`;
			}
			return;
		}

		// Split into RRULE lines, ignore DTSTART/EXRULE/RDATE etc.
		const rruleLines = s
			.split(/\r?\n/)
			.map((l) => l.trim())
			.filter((l) => l.startsWith('RRULE:'));

		// Multiple RRULE lines: only supported visually for DAILY multi-times.
		if (rruleLines.length > 1) {
			const allDaily = rruleLines.every((l) => {
				const p = parseSingleRrule(l);
				return p.FREQ === 'DAILY' && !p.BYDAY && !p.BYMONTHDAY;
			});
			if (allDaily) {
				const times = rruleLines.map((l) => {
					const p = parseSingleRrule(l);
					const h = parseInt((p.BYHOUR || '9').split(',')[0]);
					const m = parseInt((p.BYMINUTE || '0').split(',')[0]);
					return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
				});
				const sorted = dedupeSortedTimes(times);
				frequency = 'DAILY';
				dailyTimes = sorted;
				const [fh, fm] = sorted[0].split(':').map(Number);
				hour = fh;
				minute = fm;
				const firstParts = parseSingleRrule(rruleLines[0]);
				interval = parseInt(firstParts.INTERVAL || '1');
				return;
			}
			// Fallback: too complex for the visual editor, treat as CUSTOM.
			frequency = 'CUSTOM';
			customRrule = s;
			return;
		}

		const line = rruleLines[0] || s;
		const parts = parseSingleRrule(line);
		const freq = parts.FREQ || 'DAILY';
		if (!['HOURLY', 'DAILY', 'WEEKLY', 'MONTHLY'].includes(freq)) {
			frequency = 'CUSTOM';
			customRrule = s;
			return;
		}
		frequency = freq;
		interval = parseInt(parts.INTERVAL || '1');

		// BYHOUR may contain multiple values (legacy single-line multi-times).
		const byHours = (parts.BYHOUR || '9').split(',').map((v) => parseInt(v));
		const byMinutes = (parts.BYMINUTE || '0').split(',').map((v) => parseInt(v));
		hour = byHours[0];
		minute = byMinutes[0];

		if (freq === 'DAILY') {
			// Expand multi-BYHOUR (cartesian with BYMINUTE) into discrete times.
			const times: string[] = [];
			for (const h of byHours) {
				for (const m of byMinutes) {
					times.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
				}
			}
			dailyTimes = dedupeSortedTimes(times);
		}

		selectedDays = parts.BYDAY ? parts.BYDAY.split(',') : [];
		monthDay = parseInt(parts.BYMONTHDAY || '1');
	};

	export const getScheduleLabel = (): string => {
		if (frequency === 'ONCE') return $i18n.t('Once');
		if (frequency === 'HOURLY') return $i18n.t('Hourly');
		if (frequency === 'DAILY') return $i18n.t('Daily');
		if (frequency === 'WEEKLY') return $i18n.t('Weekly');
		if (frequency === 'MONTHLY') return $i18n.t('Monthly');
		if (frequency === 'CUSTOM') return $i18n.t('Custom');
		return $i18n.t('Schedule');
	};

	$: scheduleLabel = (() => {
		if (frequency === 'ONCE') return $i18n.t('Once');
		if (frequency === 'HOURLY') return $i18n.t('Hourly');
		if (frequency === 'DAILY') return $i18n.t('Daily');
		if (frequency === 'WEEKLY') return $i18n.t('Weekly');
		if (frequency === 'MONTHLY') return $i18n.t('Monthly');
		if (frequency === 'CUSTOM') return $i18n.t('Custom');
		return $i18n.t('Schedule');
	})();

	// Find the first candidate "HH:MM" not already present in the list.
	// Strategy: start 1h after the last entry, then walk forward by 30min,
	// wrapping past midnight if needed. Returns null only if all 48 half-hour
	// slots are already taken (unlikely in practice).
	const findFreeTimeSlot = (): string | null => {
		const existing = new Set(dailyTimes);
		const last = dailyTimes[dailyTimes.length - 1] || '09:00';
		const [lh, lm] = last.split(':').map(Number);
		let total = (lh * 60 + lm + 60) % (24 * 60); // start 1h after last
		for (let step = 0; step < 48; step++) {
			const h = Math.floor(total / 60);
			const m = total % 60;
			const candidate = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
			if (!existing.has(candidate)) return candidate;
			total = (total + 30) % (24 * 60);
		}
		return null;
	};

	const addDailyTime = () => {
		const candidate = findFreeTimeSlot();
		if (!candidate) {
			toast.error($i18n.t('No available time slots left in a day'));
			return;
		}
		dailyTimes = [...dailyTimes, candidate];
		const [fh, fm] = dailyTimes[0].split(':').map(Number);
		hour = fh;
		minute = fm;
		onChange();
	};

	const removeDailyTime = (idx: number) => {
		if (dailyTimes.length <= 1) return;
		dailyTimes = dailyTimes.filter((_, i) => i !== idx);
		const [fh, fm] = dailyTimes[0].split(':').map(Number);
		hour = fh;
		minute = fm;
		onChange();
	};

	const updateDailyTime = (idx: number, value: string) => {
		const prev = dailyTimes[idx];
		const next = dailyTimes.map((t, i) => (i === idx ? value : t));
		dailyTimes = next;
		const [fh, fm] = (next[0] || '09:00').split(':').map(Number);
		hour = fh;
		minute = fm;
		// Toast only on the transition into a duplicate state to avoid spam while typing.
		if (prev !== value) {
			const prevCount = dailyTimes.filter((t, i) => i !== idx && t === prev).length;
			const newCount = next.filter((t) => t === value).length;
			const wasDuplicateBefore = prevCount >= 1; // the row used to share `prev` with another
			const isDuplicateNow = newCount > 1;
			if (isDuplicateNow && !wasDuplicateBefore) {
				toast.warning(
					$i18n.t('Duplicate time {{time}} — it will be merged on save.', { time: value })
				);
			}
		}
		onChange();
	};
</script>

<Dropdown bind:show={showDropdown} {side} {align}>
	<button
		type="button"
		class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-2xl text-xs transition
			text-gray-600 dark:text-gray-400 hover:bg-black/5 dark:hover:bg-white/5"
	>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
			stroke-width="1.5"
			stroke="currentColor"
			class="size-3.5"
		>
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
			/>
		</svg>
		<span class="whitespace-nowrap">{scheduleLabel}</span>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
			stroke-width="2"
			stroke="currentColor"
			class="size-2.5"
		>
			<path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
		</svg>
	</button>

	<div
		slot="content"
		class="rounded-2xl shadow-lg border border-gray-200 dark:border-gray-800 flex flex-col bg-white dark:bg-gray-850 w-72 p-1.5"
	>
		<div class="px-1.5 pt-0.5 pb-1 text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
			{$i18n.t('Schedule')}
		</div>

		<div class="px-1 pb-1.5">
			<div class="grid grid-cols-5 gap-0.5">
				{#each FREQUENCIES as f}
					<button
						type="button"
						class="px-1 py-1.5 text-xs rounded-xl transition text-center whitespace-nowrap {frequency === f.key
							? 'bg-gray-100 dark:bg-gray-800 text-black dark:text-gray-100 font-medium'
							: 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50'}"
						on:click={(e) => {
							e.stopPropagation();
							frequency = f.key;
							onChange();
						}}
					>
						{f.label}
					</button>
				{/each}
			</div>
		</div>

		{#if frequency === 'CUSTOM'}
			<div class="px-1.5 pb-1.5">
				<input
					type="text"
					bind:value={customRrule}
					placeholder="RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
					class="w-full bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800 rounded-xl px-2.5 py-1.5 outline-hidden text-xs placeholder:text-gray-400 dark:placeholder:text-gray-600 focus:border-gray-300 dark:focus:border-gray-700 transition"
					on:click={(e) => e.stopPropagation()}
					on:input={onChange}
				/>
			</div>
		{:else if frequency === 'DAILY'}
			<div class="px-1.5 pb-1.5 flex flex-col gap-1.5">
				<div class="flex items-center justify-between px-0.5">
					<span class="text-xs text-gray-500 dark:text-gray-400">{$i18n.t('Times per day')}</span>
					<button
						type="button"
						class="flex items-center gap-0.5 text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 px-1.5 py-0.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition"
						on:click={(e) => {
							e.stopPropagation();
							addDailyTime();
						}}
						title={$i18n.t('Add time')}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
							stroke-width="2"
							stroke="currentColor"
							class="size-3"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
						</svg>
						{$i18n.t('Add')}
					</button>
				</div>
				<div class="flex flex-col gap-1 max-h-44 overflow-y-auto scrollbar-thin">
					{#each dailyTimes as t, idx (idx)}
						<div class="flex items-center gap-1.5">
							<input
								type="time"
								value={t}
								on:input={(e) => updateDailyTime(idx, e.currentTarget.value)}
								on:click={(e) => e.stopPropagation()}
								class="flex-1 bg-gray-50 dark:bg-gray-800/50 text-center outline-hidden text-xs dark:color-scheme-dark px-2 py-1.5 rounded-xl border transition {duplicateTimeSet.has(
									t
								)
									? 'border-red-400 dark:border-red-500/70 text-red-600 dark:text-red-400'
									: 'border-gray-100 dark:border-gray-800 focus:border-gray-300 dark:focus:border-gray-700'}"
								title={duplicateTimeSet.has(t) ? $i18n.t('Duplicate time') : ''}
							/>
							{#if dailyTimes.length > 1}
								<button
									type="button"
									class="text-gray-400 hover:text-red-500 p-1 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition"
									on:click={(e) => {
										e.stopPropagation();
										removeDailyTime(idx);
									}}
									title={$i18n.t('Remove')}
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										fill="none"
										viewBox="0 0 24 24"
										stroke-width="1.5"
										stroke="currentColor"
										class="size-3.5"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M6 18 18 6M6 6l12 12"
										/>
									</svg>
								</button>
							{/if}
						</div>
					{/each}
				</div>
				{#if hasDuplicateTimes}
					<div class="text-[11px] text-red-500 dark:text-red-400 px-0.5">
						{$i18n.t('Duplicate times will be merged automatically on save.')}
					</div>
				{/if}
			</div>
		{:else if frequency !== 'HOURLY'}
			<div class="flex gap-1.5 flex-wrap items-center px-1.5 pb-1.5 text-xs">
				{#if frequency === 'ONCE'}
					<div class="flex-1 min-w-0">
						<input
							type="date"
							bind:value={onceDate}
							min={new Date().toISOString().split('T')[0]}
							class="w-full bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800 rounded-xl px-2.5 py-1.5 outline-hidden text-xs dark:color-scheme-dark focus:border-gray-300 dark:focus:border-gray-700 transition"
							on:click={(e) => e.stopPropagation()}
							on:input={onChange}
						/>
					</div>
					<div class="flex-1 min-w-0">
						<input
							type="time"
							bind:value={onceTime}
							class="w-full bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800 rounded-xl px-2.5 py-1.5 outline-hidden text-xs dark:color-scheme-dark text-center focus:border-gray-300 dark:focus:border-gray-700 transition"
							on:click={(e) => e.stopPropagation()}
							on:input={onChange}
						/>
					</div>
				{:else}
					<div class="flex items-center gap-1.5 flex-1 min-w-0">
						<span class="text-xs text-gray-500 dark:text-gray-400 shrink-0">{$i18n.t('Time')}</span>
						<input
							type="time"
							value={`${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`}
							on:input={(e) => {
								const [h, m] = e.currentTarget.value.split(':').map(Number);
								hour = h;
								minute = m;
								onChange();
							}}
							class="flex-1 min-w-0 bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800 rounded-xl px-2.5 py-1.5 text-center outline-hidden text-xs dark:color-scheme-dark focus:border-gray-300 dark:focus:border-gray-700 transition"
							on:click={(e) => e.stopPropagation()}
						/>
					</div>
				{/if}

				{#if frequency === 'MONTHLY'}
					<div class="flex items-center gap-1">
						<span class="text-xs text-gray-500 dark:text-gray-400 shrink-0">{$i18n.t('Day of month prefix')}</span>
						<input
							type="number"
							bind:value={monthDay}
							min={1}
							max={31}
							class="w-12 bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800 rounded-xl px-2 py-1.5 text-center outline-hidden text-xs focus:border-gray-300 dark:focus:border-gray-700 transition"
							on:click={(e) => e.stopPropagation()}
							on:input={onChange}
						/>
						<span class="text-xs text-gray-500 dark:text-gray-400 shrink-0">{$i18n.t('Day of month suffix')}</span>
					</div>
				{/if}
			</div>

			{#if frequency === 'WEEKLY'}
				<div class="flex gap-1 px-1.5 pb-1.5">
					{#each DAYS as d}
						<button
							type="button"
							class="flex-1 py-1.5 text-xs rounded-xl transition {selectedDays.includes(d.key)
								? 'bg-gray-100 dark:bg-gray-800 text-black dark:text-gray-100 font-medium'
								: 'text-gray-500 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/50 hover:text-gray-700 dark:hover:text-gray-200'}"
							on:click={() => {
								if (selectedDays.includes(d.key)) {
									selectedDays = selectedDays.filter((x) => x !== d.key);
								} else {
									selectedDays = [...selectedDays, d.key];
								}
								onChange();
							}}
						>
							{d.label}
						</button>
					{/each}
				</div>
			{/if}
		{/if}
	</div>
</Dropdown>
