<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import type { CalendarEventModel, CalendarModel } from '$lib/apis/calendar';
	import CalendarEventChip from './CalendarEventChip.svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let events: CalendarEventModel[] = [];
	export let calendars: CalendarModel[] = [];
	export let visibleCalendarIds: Set<string> = new Set();
	export let view: 'month' | 'week' | 'day' = 'month';
	export let currentDate: Date = new Date();

	const NS = 1_000_000;
	const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

	$: calColorMap = calendars.reduce(
		(acc, c) => ({ ...acc, [c.id]: c.color }),
		{} as Record<string, string | null>
	);
	$: filteredEvents = events.filter((e) => visibleCalendarIds.has(e.calendar_id));

	// 按天分组（用于月视图）
	$: eventsByDay = (() => {
		const map: Record<string, CalendarEventModel[]> = {};
		for (const e of filteredEvents) {
			const startMs = e.start_at / NS;
			const endMs = (e.end_at || e.start_at) / NS;
			const startDate = new Date(startMs);
			const endDate = new Date(endMs);
			const d = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
			const last = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate()).getTime();
			while (d.getTime() <= last) {
				const key = d.getTime().toString();
				(map[key] ??= []).push(e);
				d.setDate(d.getDate() + 1);
			}
		}
		return map;
	})();

	$: monthStart = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
	$: calendarStart = (() => {
		const d = new Date(monthStart);
		d.setDate(d.getDate() - d.getDay());
		return d;
	})();

	$: monthDays = (() => {
		const days: Date[] = [];
		const d = new Date(calendarStart);
		for (let i = 0; i < 42; i++) {
			days.push(new Date(d));
			d.setDate(d.getDate() + 1);
		}
		return days;
	})();

	$: weekStart = (() => {
		const d = new Date(currentDate);
		d.setDate(d.getDate() - d.getDay());
		d.setHours(0, 0, 0, 0);
		return d;
	})();

	$: weekDays = (() => {
		const days: Date[] = [];
		const d = new Date(weekStart);
		for (let i = 0; i < 7; i++) {
			days.push(new Date(d));
			d.setDate(d.getDate() + 1);
		}
		return days;
	})();

	$: hours = Array.from({ length: 24 }, (_, i) => i);

	function isToday(d: Date): boolean {
		return d.toDateString() === new Date().toDateString();
	}

	function isCurrentMonth(d: Date): boolean {
		return d.getMonth() === currentDate.getMonth();
	}

	function isWeekend(d: Date): boolean {
		return d.getDay() === 0 || d.getDay() === 6;
	}

	function getEventsForHour(
		day: Date,
		hour: number,
		eventsList: CalendarEventModel[] = filteredEvents
	): CalendarEventModel[] {
		const hourStartMs = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour).getTime();
		const hourEndMs = hourStartMs + 3_600_000;
		return eventsList.filter((e) => {
			const startMs = e.start_at / NS;
			return startMs >= hourStartMs && startMs < hourEndMs;
		});
	}

	function formatHour(h: number): string {
		// 24 小时制更紧凑
		return `${String(h).padStart(2, '0')}:00`;
	}

	function handleDayClick(day: Date) {
		currentDate = day;
		const ms = new Date(day.getFullYear(), day.getMonth(), day.getDate(), 9).getTime();
		dispatch('createEvent', { start_at: ms * NS });
	}

	function goToDayView(day: Date) {
		currentDate = day;
		view = 'day';
		dispatch('viewChange', view);
		dispatch('navigate', { date: currentDate });
	}

	function handleHourClick(day: Date, hour: number) {
		currentDate = day;
		const ms = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour).getTime();
		dispatch('createEvent', { start_at: ms * NS });
	}

	function handleEventClick(event: CalendarEventModel) {
		dispatch('eventClick', event);
	}
</script>

<div class="flex flex-col h-full w-full min-h-0 min-w-0">
	<!-- 月视图 -->
	{#if view === 'month'}
		<div class="flex-1 flex flex-col min-h-0 pl-1 pr-3 pb-3 pt-1">
			<div class="flex-1 relative min-h-0 calendar-card rounded-2xl">
				<!-- 装饰光斑 -->
				<div class="pointer-events-none absolute inset-0 rounded-2xl overflow-hidden">
					<div class="absolute -top-24 -left-16 w-64 h-64 rounded-full bg-blue-400/12 dark:bg-blue-500/10 blur-3xl"></div>
					<div class="absolute top-1/3 -right-20 w-72 h-72 rounded-full bg-fuchsia-300/10 dark:bg-fuchsia-500/8 blur-3xl"></div>
					<div class="absolute -bottom-24 left-1/3 w-64 h-64 rounded-full bg-emerald-300/8 dark:bg-emerald-500/8 blur-3xl"></div>
				</div>

				<div
					class="absolute inset-0 flex flex-col rounded-2xl overflow-hidden bg-white/90 dark:bg-gray-900/80 backdrop-blur-xl border border-gray-200 dark:border-gray-700/70 shadow-[0_2px_8px_rgba(99,102,241,0.05)] dark:shadow-[0_2px_8px_rgba(0,0,0,0.2)]"
				>
					<div
						class="grid grid-cols-7 shrink-0 border-b border-gray-200/80 dark:border-gray-700/60 bg-gradient-to-r from-blue-50 via-indigo-50/80 to-fuchsia-50/70 dark:from-blue-900/25 dark:via-indigo-900/20 dark:to-fuchsia-900/15"
					>
						{#each DAY_NAMES as day, i}
							<div
								class="px-2 py-2.5 text-xs font-semibold text-center tracking-wide
								{i === 0 || i === 6 ? 'text-rose-500 dark:text-rose-300' : 'text-indigo-700 dark:text-indigo-200'}
								{i > 0 ? 'border-l border-gray-200/70 dark:border-gray-700/50' : ''}"
							>
								{$i18n.t(day)}
							</div>
						{/each}
					</div>

					<div class="flex-1 grid grid-cols-7 auto-rows-fr min-h-0">
					{#each monthDays as day, i}
						{@const dayKey = new Date(day.getFullYear(), day.getMonth(), day.getDate())
							.getTime()
							.toString()}
						{@const dayEvents = eventsByDay[dayKey] || []}
						{@const col = i % 7}
						{@const row = Math.floor(i / 7)}
						{@const today = isToday(day)}
						{@const inMonth = isCurrentMonth(day)}
						<button
							class="p-1.5 min-h-0 text-left overflow-hidden transition cursor-pointer flex flex-col group relative
								{inMonth ? '' : 'bg-gray-50/50 dark:bg-gray-900/50'}
								{today ? 'bg-gradient-to-br from-blue-100/70 via-indigo-50/50 to-transparent dark:from-blue-900/25 dark:via-indigo-900/15 dark:to-transparent' : ''}
								hover:bg-gradient-to-br hover:from-blue-50 hover:to-indigo-50/60 dark:hover:from-blue-900/20 dark:hover:to-indigo-900/15
								{col > 0 ? 'border-l border-gray-200/70 dark:border-gray-700/50' : ''}
								{row > 0 ? 'border-t border-gray-200/70 dark:border-gray-700/50' : ''}"
							on:click={() => handleDayClick(day)}
						>
							<div class="flex items-center justify-between px-0.5 mb-1">
								<span
									class="text-xs font-semibold w-6 h-6 flex items-center justify-center rounded-full transition
									{today
										? 'bg-gradient-to-br from-blue-500 to-indigo-500 text-white shadow-sm shadow-blue-500/20'
										: inMonth
											? isWeekend(day)
												? 'text-rose-500 dark:text-rose-300'
												: 'text-gray-800 dark:text-gray-200'
											: 'text-gray-400 dark:text-gray-600'}"
								>
									{day.getDate()}
								</span>
							{#if dayEvents.length > 0}
								<span class="text-[10px] text-indigo-400 dark:text-indigo-300 opacity-0 group-hover:opacity-100 transition font-medium">
									{$i18n.t('Total {{count}} items', { count: dayEvents.length })}
								</span>
							{/if}
							</div>
							<div class="flex flex-col gap-0.5 flex-1 overflow-hidden">
								{#each dayEvents.slice(0, 3) as evt (evt.instance_id || evt.id)}
									<CalendarEventChip
										event={evt}
										calendarColor={calColorMap[evt.calendar_id]}
										on:click={() => handleEventClick(evt)}
									/>
								{/each}
								{#if dayEvents.length > 3}
									<!-- svelte-ignore a11y-click-events-have-key-events --><!-- svelte-ignore a11y-no-static-element-interactions -->
									<div
										class="text-[10px] text-indigo-500/80 dark:text-indigo-300/80 px-1 mt-auto hover:text-indigo-700 dark:hover:text-indigo-200 text-left w-full truncate z-10 font-medium"
										on:click|stopPropagation={() => goToDayView(day)}
									>
										{$i18n.t('+{{count}} more', { count: dayEvents.length - 3 })}
									</div>
								{/if}
							</div>
						</button>
					{/each}
					</div>
				</div>
			</div>
		</div>

		<!-- 周视图 -->
	{:else if view === 'week'}
		<div class="flex-1 flex flex-col min-h-0 pl-1 pr-3 pb-3 pt-1">
			<div class="flex-1 relative min-h-0 calendar-card rounded-2xl">
				<div class="pointer-events-none absolute inset-0 rounded-2xl overflow-hidden">
					<div class="absolute -top-24 -left-16 w-64 h-64 rounded-full bg-blue-400/12 dark:bg-blue-500/10 blur-3xl"></div>
					<div class="absolute top-1/3 -right-20 w-72 h-72 rounded-full bg-fuchsia-300/10 dark:bg-fuchsia-500/8 blur-3xl"></div>
					<div class="absolute -bottom-24 left-1/3 w-64 h-64 rounded-full bg-emerald-300/8 dark:bg-emerald-500/8 blur-3xl"></div>
				</div>

				<div
					class="absolute inset-0 rounded-2xl bg-white/90 dark:bg-gray-900/80 backdrop-blur-xl border border-gray-200 dark:border-gray-700/70 shadow-[0_2px_8px_rgba(99,102,241,0.05)] dark:shadow-[0_2px_8px_rgba(0,0,0,0.2)] overflow-hidden"
				>
					<div class="absolute inset-0 overflow-x-auto flex flex-col">
						<div class="min-w-[700px] flex flex-col flex-1">
							<div
								class="grid grid-cols-[64px_repeat(7,1fr)] shrink-0 border-b border-gray-200/80 dark:border-gray-700/60 bg-gradient-to-r from-blue-50 via-indigo-50/80 to-fuchsia-50/70 dark:from-blue-900/25 dark:via-indigo-900/20 dark:to-fuchsia-900/15"
							>
								<div></div>
								{#each weekDays as day}
									<div
										class="text-center py-3 {day.getDay() > 0
											? 'border-l border-gray-200/70 dark:border-gray-700/50'
											: ''}"
									>
										<div
											class="text-[11px] font-semibold tracking-wide {day.getDay() === 0 || day.getDay() === 6
												? 'text-rose-500 dark:text-rose-300'
												: 'text-indigo-700 dark:text-indigo-200'}"
										>
											{$i18n.t(DAY_NAMES[day.getDay()])}
										</div>
										<div
											class="text-sm mt-1 w-8 h-8 flex items-center justify-center mx-auto rounded-full font-semibold transition {isToday(
												day
											)
												? 'bg-gradient-to-br from-blue-500 to-indigo-500 text-white shadow-sm shadow-blue-500/20'
												: 'text-gray-800 dark:text-gray-200'}"
										>
											{day.getDate()}
										</div>
									</div>
								{/each}
							</div>

							<div class="flex-1 overflow-y-auto">
								{#each hours as hour}
									<div
										class="grid grid-cols-[64px_repeat(7,1fr)] min-h-[60px] {hour > 0
											? 'border-t border-gray-200/70 dark:border-gray-700/50'
											: ''}"
									>
										<div
											class="relative text-xs text-gray-600 dark:text-gray-300 select-none font-medium tabular-nums"
										>
											{#if hour > 0}
												<span class="absolute -top-2 right-3 px-1.5 rounded bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm">
													{formatHour(hour)}
												</span>
											{/if}
										</div>
										{#each weekDays as day}
											{@const hourEvents = getEventsForHour(day, hour, filteredEvents)}
											{@const today = isToday(day)}
											<button
												class="px-1 py-1 {day.getDay() > 0
													? 'border-l border-gray-200/70 dark:border-gray-700/50'
													: ''} hover:bg-gradient-to-br hover:from-blue-50 hover:to-indigo-50/60 dark:hover:from-blue-900/20 dark:hover:to-indigo-900/15 transition cursor-pointer min-w-0 flex flex-col {today
													? 'bg-gradient-to-b from-blue-50/60 to-transparent dark:from-blue-900/20 dark:to-transparent'
													: ''}"
												on:click={() => handleHourClick(day, hour)}
											>
												<div class="flex flex-col gap-0.5 w-full min-h-0">
													{#each hourEvents.slice(0, 3) as evt (evt.instance_id || evt.id)}
														<CalendarEventChip
															event={evt}
															calendarColor={calColorMap[evt.calendar_id]}
															on:click={() => handleEventClick(evt)}
														/>
													{/each}
													{#if hourEvents.length > 3}
														<!-- svelte-ignore a11y-click-events-have-key-events --><!-- svelte-ignore a11y-no-static-element-interactions -->
														<div
															class="text-[10px] text-indigo-500/80 dark:text-indigo-300/80 px-1 mt-auto hover:text-indigo-700 dark:hover:text-indigo-200 text-left w-full truncate z-10 font-medium"
															on:click|stopPropagation={() => goToDayView(day)}
														>
															{$i18n.t('+{{count}} more', { count: hourEvents.length - 3 })}
														</div>
													{/if}
												</div>
											</button>
										{/each}
									</div>
								{/each}
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- 日视图 -->
	{:else}
		<div class="flex-1 flex flex-col min-h-0 pl-1 pr-3 pb-3 pt-1">
			<div class="flex-1 relative min-h-0 calendar-card rounded-2xl">
				<div class="pointer-events-none absolute inset-0 rounded-2xl overflow-hidden">
					<div class="absolute -top-24 -left-16 w-64 h-64 rounded-full bg-blue-400/12 dark:bg-blue-500/10 blur-3xl"></div>
					<div class="absolute top-1/3 -right-20 w-72 h-72 rounded-full bg-fuchsia-300/10 dark:bg-fuchsia-500/8 blur-3xl"></div>
					<div class="absolute -bottom-24 left-1/3 w-64 h-64 rounded-full bg-emerald-300/8 dark:bg-emerald-500/8 blur-3xl"></div>
				</div>

				<div
					class="absolute inset-0 rounded-2xl overflow-hidden bg-white/90 dark:bg-gray-900/80 backdrop-blur-xl border border-gray-200 dark:border-gray-700/70 shadow-[0_2px_8px_rgba(99,102,241,0.05)] dark:shadow-[0_2px_8px_rgba(0,0,0,0.2)] overflow-y-auto"
				>
					{#each hours as hour}
						{@const hourEvents = getEventsForHour(currentDate, hour, filteredEvents)}
						<div
							class="flex min-h-[64px] {hour > 0
								? 'border-t border-gray-200/70 dark:border-gray-700/50'
								: ''}"
						>
							<div class="w-20 shrink-0 relative select-none">
								{#if hour > 0}
									<span
										class="absolute -top-2 right-3 px-1.5 rounded bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm text-xs text-gray-600 dark:text-gray-300 font-medium tabular-nums"
									>
										{formatHour(hour)}
									</span>
								{/if}
							</div>
							<button
								class="flex-1 border-l border-gray-200/70 dark:border-gray-700/50 px-3 py-1.5
									hover:bg-gradient-to-br hover:from-blue-50 hover:to-indigo-50/60 dark:hover:from-blue-900/20 dark:hover:to-indigo-900/15 transition cursor-pointer flex flex-col text-left justify-start"
								on:click={() => handleHourClick(currentDate, hour)}
							>
								<div class="flex flex-col gap-1 w-full">
									{#each hourEvents as evt (evt.instance_id || evt.id)}
										<CalendarEventChip
											event={evt}
											calendarColor={calColorMap[evt.calendar_id]}
											on:click={() => handleEventClick(evt)}
										/>
									{/each}
								</div>
							</button>
						</div>
					{/each}
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.calendar-card {
		isolation: isolate;
	}
</style>
