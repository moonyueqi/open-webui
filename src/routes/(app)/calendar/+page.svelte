<script lang="ts">
	import { onMount, getContext, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { WEBUI_NAME, mobile, showSidebar } from '$lib/stores';
	import {
		getCalendars,
		getCalendarEvents,
		deleteCalendar,
		type CalendarModel,
		type CalendarEventModel
	} from '$lib/apis/calendar';
	import CalendarView from '$lib/components/calendar/CalendarView.svelte';
	import CalendarSidebar from '$lib/components/calendar/CalendarSidebar.svelte';
	import CalendarEventModal from '$lib/components/calendar/CalendarEventModal.svelte';
	import CreateCalendarModal from '$lib/components/calendar/CreateCalendarModal.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import Select from '$lib/components/calendar/_Select.svelte';
	import Check from '$lib/components/icons/Check.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';

	const i18n = getContext('i18n');

	let loaded = false;
	let calendars: CalendarModel[] = [];
	let events: CalendarEventModel[] = [];
	let visibleCalendarIds: Set<string> = new Set();

	let view: 'month' | 'week' | 'day' = 'month';
	let currentDate = new Date();

	let showEventModal = false;
	let editEvent: CalendarEventModel | null = null;
	let defaultStartAt: number | null = null;
	let showCreateCalendarModal = false;

	function getVisibleRange(): { start: string; end: string } {
		const d = new Date(currentDate);
		let start: Date;
		let end: Date;

		if (view === 'month') {
			start = new Date(d.getFullYear(), d.getMonth(), 1);
			start.setDate(start.getDate() - start.getDay());
			end = new Date(start);
			end.setDate(end.getDate() + 42);
		} else if (view === 'week') {
			start = new Date(d);
			start.setDate(start.getDate() - start.getDay());
			start.setHours(0, 0, 0, 0);
			end = new Date(start);
			end.setDate(end.getDate() + 7);
		} else {
			start = new Date(d.getFullYear(), d.getMonth(), d.getDate());
			end = new Date(start);
			end.setDate(end.getDate() + 1);
		}

		return {
			start: start.toISOString(),
			end: end.toISOString()
		};
	}

	async function loadCalendars() {
		try {
			calendars = (await getCalendars(localStorage.token)) ?? [];
			visibleCalendarIds = new Set(calendars.map((c) => c.id));
		} catch (err) {
			console.error('loadCalendars', err);
			calendars = [];
		}
	}

	async function loadEvents() {
		try {
			const { start, end } = getVisibleRange();
			events = await getCalendarEvents(localStorage.token, start, end);
		} catch (err) {
			toast.error(`${err}`);
		}
	}

	async function refresh() {
		await loadEvents();
	}

	function toggleCalendar(id: string) {
		const next = new Set(visibleCalendarIds);
		if (next.has(id)) {
			next.delete(id);
		} else {
			next.add(id);
		}
		visibleCalendarIds = next;
	}

	async function handleDeleteCalendar(id: string) {
		try {
			const result = await deleteCalendar(localStorage.token, id);
			if (result) {
				toast.success($i18n.t('Calendar deleted'));
				await loadCalendars();
				await refresh();
			} else {
				toast.error($i18n.t('Failed to delete calendar'));
			}
		} catch (err) {
			toast.error(`${err}`);
		}
	}

	function handleCreateEvent(e: CustomEvent<{ start_at: number }>) {
		editEvent = null;
		defaultStartAt = e.detail.start_at;
		showEventModal = true;
	}

	function handleEventClick(e: CustomEvent<CalendarEventModel>) {
		const evt = e.detail;
		if (evt.meta?.automation_id) {
			if (evt.meta?.chat_id) {
				goto(`/c/${evt.meta.chat_id}`);
			} else {
				goto(`/automations/${evt.meta.automation_id}`);
			}
			return;
		}
		editEvent = evt;
		defaultStartAt = null;
		showEventModal = true;
	}

	async function handleNavigate() {
		await tick();
		refresh();
	}

	async function handleDateSelect(date: Date) {
		currentDate = date;
		await tick();
		refresh();
	}

	function handleCreateCalendar() {
		showCreateCalendarModal = true;
	}

	async function handleCalendarCreated() {
		await loadCalendars();
		await refresh();
	}

	function handleNewEvent() {
		editEvent = null;
		defaultStartAt = null;
		showEventModal = true;
	}

	function navigateCalendar(delta: number) {
		const d = new Date(currentDate);
		if (view === 'month') {
			d.setDate(1);
			d.setMonth(d.getMonth() + delta);
		} else if (view === 'week') d.setDate(d.getDate() + delta * 7);
		else d.setDate(d.getDate() + delta);
		currentDate = d;
		handleNavigate();
	}

	function goToToday() {
		currentDate = new Date();
		handleNavigate();
	}

	$: defaultCalendarId =
		calendars.find((c) => c.is_default && c.id !== '__scheduled_tasks__')?.id ||
		calendars.find((c) => c.id !== '__scheduled_tasks__')?.id ||
		'';

	// 本地化的标题文案
	$: weekdayShort = $i18n.t(
		['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][currentDate.getDay()]
	);

	$: headerText =
		view === 'day'
			? $i18n.t('{{year}}年{{month}}月{{day}}日 {{weekday}}', {
					year: currentDate.getFullYear(),
					month: currentDate.getMonth() + 1,
					day: currentDate.getDate(),
					weekday: weekdayShort
				})
			: view === 'week'
				? (() => {
						const start = new Date(currentDate);
						start.setDate(start.getDate() - start.getDay());
						const end = new Date(start);
						end.setDate(end.getDate() + 6);
						return $i18n.t('{{year}}年{{month}}月 第{{week}}周', {
							year: start.getFullYear(),
							month: start.getMonth() + 1,
							week: Math.ceil((start.getDate() + 6 - start.getDay()) / 7)
						});
					})()
				: $i18n.t('{{year}}年{{month}}月', {
						year: currentDate.getFullYear(),
						month: currentDate.getMonth() + 1
					});

	onMount(async () => {
		await loadCalendars();
		await refresh();
		loaded = true;
	});
</script>

<svelte:head>
	<title>{$i18n.t('Task Calendar')} • {$WEBUI_NAME}</title>
</svelte:head>

<CalendarEventModal
	bind:show={showEventModal}
	event={editEvent}
	{calendars}
	{defaultCalendarId}
	{defaultStartAt}
	on:save={() => refresh()}
	on:delete={() => refresh()}
/>

<CreateCalendarModal bind:show={showCreateCalendarModal} on:created={handleCalendarCreated} />

<div
	class="flex flex-col w-full h-full max-h-full transition-width duration-200 ease-in-out"
>
	{#if loaded}
		<!-- 顶部导航 -->
		<nav class="px-4 pt-2 pb-2 backdrop-blur-xl drag-region select-none shrink-0">
			<div class="flex items-center gap-2">
				{#if $mobile}
					<div class="{$showSidebar ? 'md:hidden' : ''} flex flex-none items-center">
						<Tooltip
							content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
							interactive={true}
						>
							<button
								id="sidebar-toggle-button"
								class="cursor-pointer flex rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition"
								on:click={() => showSidebar.set(!$showSidebar)}
							>
								<div class="self-center p-1.5">
									<SidebarIcon />
								</div>
							</button>
						</Tooltip>
					</div>
				{/if}

				<div class="flex w-full items-center">
					<div class="flex items-center gap-2">
						<div class="flex items-center gap-2 pr-1">
							<div class="flex items-center justify-center size-7 rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-fuchsia-500 text-white shadow-sm shadow-indigo-500/20">
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="2"
									stroke="currentColor"
									class="size-4"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5"
									/>
								</svg>
							</div>
							<span class="text-sm font-semibold bg-gradient-to-r from-blue-600 via-indigo-600 to-fuchsia-600 dark:from-blue-300 dark:via-indigo-300 dark:to-fuchsia-300 bg-clip-text text-transparent">
								{$i18n.t('Task Calendar')}
							</span>
						</div>

						<div class="hidden sm:block w-px h-5 bg-gray-200 dark:bg-gray-800 mx-1"></div>

						<div class="flex items-center gap-1 py-1">
							<span class="min-w-fit px-1 text-sm font-medium text-gray-700 dark:text-gray-200 select-none"
								>{headerText}</span
							>
							<button
								class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition"
								on:click={() => navigateCalendar(-1)}
								aria-label={$i18n.t('Previous')}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="1.5"
									stroke="currentColor"
									class="size-3.5 text-gray-500"
									><path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M15.75 19.5 8.25 12l7.5-7.5"
									/></svg
								>
							</button>
							<button
								class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition"
								on:click={() => navigateCalendar(1)}
								aria-label={$i18n.t('Next')}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="1.5"
									stroke="currentColor"
									class="size-3.5 text-gray-500"
									><path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="m8.25 4.5 7.5 7.5-7.5 7.5"
									/></svg
								>
							</button>
						</div>
					</div>

					<div class="ml-auto flex items-center gap-1.5">
						<button
							class="hidden sm:inline text-xs px-3 py-1.5 rounded-xl border border-gray-200/70 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-850 transition text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white font-medium"
							on:click={goToToday}
						>
							{$i18n.t('Today')}
						</button>

						<Select
							bind:value={view}
							items={[
								{ value: 'day', label: $i18n.t('Day') },
								{ value: 'week', label: $i18n.t('Week') },
								{ value: 'month', label: $i18n.t('Month') }
							]}
							onChange={() => handleNavigate()}
							triggerClass="relative flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 dark:bg-gray-850 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl text-xs font-medium transition"
							contentClass="rounded-2xl w-40 p-1 border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-850 dark:text-white shadow-lg"
							align="end"
						>
							<svelte:fragment slot="trigger" let:selectedLabel>
								<span
									class="inline-flex h-input px-0.5 outline-hidden bg-transparent truncate line-clamp-1"
								>
									{selectedLabel}
								</span>
								<ChevronDown className="size-3.5" strokeWidth="2.5" />
							</svelte:fragment>

							<svelte:fragment slot="item" let:item let:selected>
								{item.label}
								<div class="ml-auto {selected ? '' : 'invisible'}">
									<Check />
								</div>
							</svelte:fragment>
						</Select>

						<button
							class="ml-1 px-3 py-1.5 text-xs gap-1.5 rounded-xl bg-gradient-to-r from-blue-500 via-indigo-500 to-fuchsia-500 hover:from-blue-600 hover:via-indigo-600 hover:to-fuchsia-600 text-white shadow-sm shadow-indigo-500/20 hover:shadow-md hover:shadow-indigo-500/30 transition flex items-center font-medium"
							on:click={handleNewEvent}
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="2.5"
								stroke="currentColor"
								class="size-3.5"
								><path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M12 4.5v15m7.5-7.5h-15"
								/></svg
							>

							<span class="hidden sm:inline">{$i18n.t('New Task')}</span>
						</button>
					</div>
				</div>
			</div>
		</nav>

		<div class="flex flex-1 min-h-0">
			<!-- 侧边栏 -->
			<div class="hidden md:flex flex-col w-60 shrink-0 pr-2 pl-3 pb-3 overflow-y-auto">
				<CalendarSidebar
					{calendars}
					{visibleCalendarIds}
					{currentDate}
					onToggle={toggleCalendar}
					onCreateCalendar={handleCreateCalendar}
					onDeleteCalendar={handleDeleteCalendar}
					onDateSelect={handleDateSelect}
				/>
			</div>

			<!-- 主视图 -->
			<div class="flex-1 flex flex-col min-h-0">
				<CalendarView
					{events}
					{calendars}
					{visibleCalendarIds}
					bind:view
					bind:currentDate
					on:createEvent={handleCreateEvent}
					on:eventClick={handleEventClick}
					on:navigate={handleNavigate}
					on:viewChange={handleNavigate}
				/>
			</div>
		</div>
	{:else}
		<div class="w-full h-full flex justify-center items-center">
			<Spinner className="size-5" />
		</div>
	{/if}
</div>
