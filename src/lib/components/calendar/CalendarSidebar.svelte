<script lang="ts">
	import { getContext } from 'svelte';
	import type { CalendarModel } from '$lib/apis/calendar';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

	const i18n = getContext('i18n');

	export let calendars: CalendarModel[] = [];
	export let visibleCalendarIds: Set<string> = new Set();
	export let currentDate: Date = new Date();
	export let onToggle: (id: string) => void = () => {};
	export let onCreateCalendar: () => void = () => {};
	export let onDeleteCalendar: (id: string) => void = () => {};
	export let onDateSelect: (date: Date) => void = () => {};

	// 删除确认状态
	let showDeleteConfirm = false;
	let deleteTargetCalendar: CalendarModel | null = null;

	function isDeletable(cal: CalendarModel): boolean {
		return !cal.is_default && !cal.is_system;
	}

	function handleDeleteClick(e: MouseEvent, cal: CalendarModel) {
		e.stopPropagation();
		deleteTargetCalendar = cal;
		showDeleteConfirm = true;
	}

	function confirmDelete() {
		if (deleteTargetCalendar) {
			onDeleteCalendar(deleteTargetCalendar.id);
		}
		deleteTargetCalendar = null;
	}

	// 小日历状态
	let miniMonth = currentDate.getMonth();
	let miniYear = currentDate.getFullYear();

	$: miniMonthStart = new Date(miniYear, miniMonth, 1);
	$: miniCalStart = (() => {
		const d = new Date(miniMonthStart);
		d.setDate(d.getDate() - d.getDay());
		return d;
	})();

	$: miniDays = (() => {
		const days: Date[] = [];
		const d = new Date(miniCalStart);
		for (let i = 0; i < 42; i++) {
			days.push(new Date(d));
			d.setDate(d.getDate() + 1);
		}
		return days;
	})();

	function isToday(d: Date): boolean {
		return d.toDateString() === new Date().toDateString();
	}

	function navigateMini(delta: number) {
		let m = miniMonth + delta;
		let y = miniYear;
		if (m > 11) {
			m = 0;
			y++;
		} else if (m < 0) {
			m = 11;
			y--;
		}
		miniMonth = m;
		miniYear = y;
	}

	// 系统日历名称中文化
	function displayName(cal: CalendarModel): string {
		if (cal.id === '__scheduled_tasks__' || cal.is_system) {
			return $i18n.t('Scheduled Tasks');
		}
		return cal.name;
	}
</script>

<ConfirmDialog
	bind:show={showDeleteConfirm}
	title={$i18n.t('Delete Calendar')}
	message={$i18n.t(
		'This will permanently delete the calendar "{{name}}" and all its events. This action cannot be undone.',
		{ name: deleteTargetCalendar?.name ?? '' }
	)}
	confirmLabel={$i18n.t('Delete')}
	onConfirm={confirmDelete}
/>

<div class="flex flex-col gap-5 pt-2">
	<!-- 小日历 -->
	<div class="relative rounded-2xl p-2.5 border border-gray-200 dark:border-gray-700/60 bg-gradient-to-br from-white via-blue-50/40 to-fuchsia-50/30 dark:from-gray-900/70 dark:via-blue-900/20 dark:to-fuchsia-900/15 shadow-[0_1px_4px_rgba(99,102,241,0.04)] backdrop-blur-sm">
		<div class="flex items-center justify-between px-1 mb-2">
			<div class="text-xs font-semibold text-gray-800 dark:text-gray-100">
				{$i18n.t('{{year}}年{{month}}月', { year: miniYear, month: miniMonth + 1 })}
			</div>
			<div class="flex items-center gap-0.5">
				<button
					class="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition text-gray-500 dark:text-gray-400"
					on:click={() => navigateMini(-1)}
					aria-label={$i18n.t('Previous')}
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						fill="none"
						viewBox="0 0 24 24"
						stroke-width="2.5"
						stroke="currentColor"
						class="size-2.5"
						><path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M15.75 19.5 8.25 12l7.5-7.5"
						/></svg
					>
				</button>
				<button
					class="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition text-gray-500 dark:text-gray-400"
					on:click={() => navigateMini(1)}
					aria-label={$i18n.t('Next')}
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						fill="none"
						viewBox="0 0 24 24"
						stroke-width="2.5"
						stroke="currentColor"
						class="size-2.5"
						><path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="m8.25 4.5 7.5 7.5-7.5 7.5"
						/></svg
					>
				</button>
			</div>
		</div>

		<div class="grid grid-cols-7 text-center text-[10px] text-gray-400 dark:text-gray-500 mb-0.5">
			{#each ['日', '一', '二', '三', '四', '五', '六'] as d, i}
				<div class="py-0.5 {i === 0 || i === 6 ? 'text-rose-400/70 dark:text-rose-300/60' : ''}">{d}</div>
			{/each}
		</div>

		<div class="grid grid-cols-7 text-center text-[11px]">
			{#each miniDays as day}
				{@const today = isToday(day)}
				{@const selected = day.toDateString() === currentDate.toDateString()}
				{@const inMonth = day.getMonth() === miniMonth}
				<button
					class="w-7 h-7 flex items-center justify-center rounded-full transition mx-auto
						{!inMonth ? 'text-gray-300 dark:text-gray-700' : ''}
						{today ? 'bg-gradient-to-br from-blue-500 to-indigo-500 text-white shadow-sm font-semibold' : ''}
						{selected && !today ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-semibold' : ''}
						{!today && !selected ? 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300' : ''}"
					on:click={() => onDateSelect(day)}
				>
					{day.getDate()}
				</button>
			{/each}
		</div>
	</div>

	<!-- 日历列表 -->
	<div>
		<div class="flex items-center justify-between mb-1.5 px-1">
			<div class="text-[11px] text-gray-500 dark:text-gray-400 uppercase tracking-wider font-semibold">
				{$i18n.t('My Calendars')}
			</div>
			<button
				class="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition text-gray-500 dark:text-gray-400"
				title={$i18n.t('New calendar')}
				on:click={onCreateCalendar}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="2.5"
					stroke="currentColor"
					class="size-3"
					><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg
				>
			</button>
		</div>

		<div class="flex flex-col gap-0.5">
			{#each calendars as cal (cal.id)}
				{@const visible = visibleCalendarIds.has(cal.id)}
				<div class="group flex items-center w-full">
					<button
						class="flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition
							hover:bg-gray-100/70 dark:hover:bg-gray-800/50 flex-1 text-left min-w-0"
						on:click={() => onToggle(cal.id)}
					>
						<span
							class="shrink-0 size-3 rounded-md transition-all flex items-center justify-center"
							style="background-color: {visible ? cal.color || '#3b82f6' : 'transparent'}; border: 1.5px solid {cal.color || '#3b82f6'};"
						>
							{#if visible}
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 24 24"
									fill="none"
									stroke="white"
									stroke-width="3.5"
									class="size-2"
								>
									<path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" />
								</svg>
							{/if}
						</span>
						<span
							class="truncate flex-1 {visible
								? 'text-gray-800 dark:text-gray-200'
								: 'text-gray-400 dark:text-gray-500'}"
						>
							{displayName(cal)}
						</span>

						{#if cal.is_default}
							<span class="text-[9px] text-gray-400 dark:text-gray-500 shrink-0 px-1 rounded bg-gray-100 dark:bg-gray-800">
								{$i18n.t('Default')}
							</span>
						{/if}

						{#if isDeletable(cal)}
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<span
								class="shrink-0 p-0.5 rounded opacity-0 group-hover:opacity-100
									transition-all duration-150 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500"
								role="button"
								tabindex="-1"
								title={$i18n.t('Delete calendar')}
								on:click|stopPropagation={(e) => handleDeleteClick(e, cal)}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="2"
									stroke="currentColor"
									class="size-3"
								>
									<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
								</svg>
							</span>
						{/if}
					</button>
				</div>
			{/each}
		</div>
	</div>
</div>
