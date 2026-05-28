<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Select from '$lib/components/calendar/_Select.svelte';

	import type { CalendarModel, CalendarEventModel, CalendarEventForm } from '$lib/apis/calendar';
	import {
		createCalendarEvent,
		updateCalendarEvent,
		deleteCalendarEvent
	} from '$lib/apis/calendar';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let show = false;
	export let event: CalendarEventModel | null = null;
	export let calendars: CalendarModel[] = [];
	export let defaultCalendarId: string = '';
	export let defaultStartAt: number | null = null;

	let title = '';
	let description = '';
	let calendarId = '';
	let startDate = '';
	let startTime = '';
	let endDate = '';
	let endTime = '';
	let allDay = false;
	let location = '';
	let alertMinutes: number = 10;
	let loading = false;
	let showDeleteConfirmDialog = false;


	const NS = 1_000_000;

	function nsToDateStr(ns: number): string {
		const d = new Date(ns / NS);
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}

	function nsToTimeStr(ns: number): string {
		const d = new Date(ns / NS);
		return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
	}

	function dateToDateStr(d: Date): string {
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}

	function dateToTimeStr(d: Date): string {
		return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
	}

	function dateTimeToNs(dateStr: string, timeStr: string): number {
		return new Date(`${dateStr}T${timeStr || '00:00'}`).getTime() * NS;
	}

	function reset() {
		if (event) {
			title = event.title;
			description = event.description || '';
			calendarId = event.calendar_id;
			startDate = nsToDateStr(event.start_at);
			startTime = nsToTimeStr(event.start_at);
			endDate = event.end_at ? nsToDateStr(event.end_at) : '';
			endTime = event.end_at ? nsToTimeStr(event.end_at) : '';
			allDay = event.all_day;
			location = event.location || '';
			alertMinutes = event.meta?.alert_minutes ?? 10;
		} else {
			title = '';
			description = '';
			const firstSelectable = calendars.find((c) => c.id !== '__scheduled_tasks__');
			const fallbackId =
				defaultCalendarId && defaultCalendarId !== '__scheduled_tasks__'
					? defaultCalendarId
					: firstSelectable?.id || '';
			calendarId = fallbackId;
			if (defaultStartAt) {
				startDate = nsToDateStr(defaultStartAt);
				startTime = nsToTimeStr(defaultStartAt);
				const endMs = defaultStartAt / NS + 60 * 60 * 1000;
				const endDt = new Date(endMs);
				endDate = dateToDateStr(endDt);
				endTime = dateToTimeStr(endDt);
			} else {
				const now = new Date();
				now.setSeconds(0, 0);
				startDate = dateToDateStr(now);
				startTime = dateToTimeStr(now);
				const later = new Date(now.getTime() + 60 * 60 * 1000);
				endDate = dateToDateStr(later);
				endTime = dateToTimeStr(later);
			}
			allDay = false;
			location = '';
			alertMinutes = 10;
		}
	}

	$: if (show) reset();

	function handleStartDateChange() {
		endDate = startDate;
	}

	function handleStartTimeChange() {
		if (endDate === startDate && endTime && endTime < startTime) {
			const [h, m] = startTime.split(':').map(Number);
			const total = h * 60 + m + 60;
			const eh = Math.floor(total / 60) % 24;
			const em = total % 60;
			endTime = `${String(eh).padStart(2, '0')}:${String(em).padStart(2, '0')}`;
		}
	}

	function handleEndTimeChange() {
		if (endDate === startDate && endTime && endTime < startTime) {
			endTime = startTime;
		}
	}

	$: selectableCalendars = calendars.filter((c) => c.id !== '__scheduled_tasks__');
	$: calendarItems = selectableCalendars.map((c) => ({ value: c.id, label: c.name, color: c.color }));
	$: selectedCalendar = calendars.find((c) => c.id === calendarId);
	$: calendarColor = selectedCalendar?.color || '#3b82f6';

	$: isAutomation = !!event?.meta?.automation_id;
	$: readOnly = isAutomation;

	$: alertItems = [
		{ value: -1, label: $i18n.t('None') },
		{ value: 0, label: $i18n.t('At time of event') },
		{ value: 1, label: $i18n.t('1 minute before') },
		{ value: 5, label: $i18n.t('5 minutes before') },
		{ value: 10, label: $i18n.t('10 minutes before') },
		{ value: 15, label: $i18n.t('15 minutes before') },
		{ value: 30, label: $i18n.t('30 minutes before') },
		{ value: 60, label: $i18n.t('1 hour before') }
	];

	const submitHandler = async () => {
		if (!title.trim()) {
			toast.error($i18n.t('Title is required'));
			return;
		}

		loading = true;
		try {
			const startNs = dateTimeToNs(startDate, allDay ? '00:00' : startTime);
			let endNs = endDate ? dateTimeToNs(endDate, allDay ? '23:59' : endTime) : undefined;

			if (endNs !== undefined && endNs < startNs) {
				toast.error($i18n.t('End time must be after start time'));
				loading = false;
				return;
			}

			if (event && !isAutomation) {
				const result = await updateCalendarEvent(localStorage.token, event.id, {
					calendar_id: calendarId,
					title: title.trim(),
					description: description.trim() || undefined,
					start_at: startNs,
					end_at: endNs,
					all_day: allDay,
					location: location.trim() || undefined,
					meta: { alert_minutes: alertMinutes }
				});
				if (result) {
					toast.success($i18n.t('Task updated'));
					dispatch('save', result);
					show = false;
				}
			} else {
				const form: CalendarEventForm = {
					calendar_id: calendarId,
					title: title.trim(),
					description: description.trim() || undefined,
					start_at: startNs,
					end_at: endNs,
					all_day: allDay,
					location: location.trim() || undefined,
					meta: { alert_minutes: alertMinutes }
				};
				const result = await createCalendarEvent(localStorage.token, form);
				if (result) {
					toast.success($i18n.t('Task created'));
					dispatch('save', result);
					show = false;
				}
			}
		} catch (err) {
			toast.error(`${err}`);
		} finally {
			loading = false;
		}
	};

	const deleteHandler = async () => {
		if (!event || isAutomation) return;
		loading = true;
		try {
			await deleteCalendarEvent(localStorage.token, event.id);
			toast.success($i18n.t('Task deleted'));
			dispatch('delete', event);
			show = false;
		} catch (err) {
			toast.error(`${err}`);
		} finally {
			loading = false;
		}
	};
</script>

<Modal size="md" bind:show>
	<div>
		<!-- Header -->
		<div class="flex items-center justify-between gap-2 dark:text-gray-100 px-5 pt-4 pb-2">
			<div class="flex items-center gap-3 flex-1 min-w-0">
				<div
					class="flex items-center justify-center w-9 h-9 rounded-xl shrink-0 shadow-sm"
					style="background-color: {calendarColor}1a; color: {calendarColor};"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						fill="none"
						viewBox="0 0 24 24"
						stroke-width="1.8"
						stroke="currentColor"
						class="size-5"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5"
						/>
					</svg>
				</div>
				<input
					class="w-full text-lg font-semibold bg-transparent outline-hidden font-primary placeholder:text-gray-300 dark:placeholder:text-gray-700 disabled:opacity-70"
					type="text"
					bind:value={title}
					placeholder={$i18n.t('Task title')}
					disabled={readOnly}
				/>
			</div>
			<button
				class="self-center shrink-0 p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition"
				aria-label={$i18n.t('Close')}
				on:click={() => (show = false)}
			>
				<XMark className="size-5" />
			</button>
		</div>

		{#if isAutomation}
			<div class="px-5 pt-2">
				<div
					class="text-xs px-3 py-2 rounded-xl bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border border-amber-100 dark:border-amber-900/30 flex items-center gap-2"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 24 24"
						fill="currentColor"
						class="size-3.5 shrink-0"
					>
						<path
							fill-rule="evenodd"
							d="M14.615 1.595a.75.75 0 0 1 .359.852L12.982 9.75h7.268a.75.75 0 0 1 .548 1.262l-10.5 11.25a.75.75 0 0 1-1.272-.71l1.992-7.302H3.75a.75.75 0 0 1-.548-1.262l10.5-11.25a.75.75 0 0 1 .913-.143Z"
							clip-rule="evenodd"
						/>
					</svg>
					{$i18n.t('This task is managed by an automation and cannot be edited here.')}
				</div>
			</div>
		{/if}

		<!-- Form -->
		<div class="px-5 pt-3 pb-2 flex flex-col gap-3">
			<!-- 日历 -->
			<div class="flex items-center gap-3">
				<div class="w-20 text-sm font-medium text-gray-600 dark:text-gray-300 shrink-0">
					{$i18n.t('Calendar')}
				</div>
				<div class="flex-1 min-w-0">
					<Select
						value={calendarId}
						items={calendarItems}
						onChange={(v) => (calendarId = v)}
						triggerClass="w-full flex items-center justify-between gap-2 text-sm bg-gray-50 dark:bg-gray-850/60 hover:bg-gray-100 dark:hover:bg-gray-800 px-3 py-2 rounded-xl border border-transparent text-gray-800 dark:text-gray-200 transition disabled:cursor-not-allowed disabled:opacity-60"
						itemClass="flex w-full gap-2 items-center text-left px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
						align="start"
					>
						<svelte:fragment slot="trigger" let:selectedLabel let:open>
							<span class="truncate text-left flex-1">{selectedLabel || $i18n.t('Select')}</span>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 20 20"
								fill="currentColor"
								class="size-4 text-gray-400 shrink-0 transition-transform {open
									? 'rotate-180'
									: ''}"
							>
								<path
									fill-rule="evenodd"
									d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.06l3.71-3.83a.75.75 0 1 1 1.08 1.04l-4.25 4.39a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z"
									clip-rule="evenodd"
								/>
							</svg>
						</svelte:fragment>
						<svelte:fragment slot="item" let:item let:selected>
							<span
								class="size-2.5 rounded-full shrink-0"
								style="background-color: {item.color || '#3b82f6'};"
							></span>
							<span class="truncate flex-1">{item.label}</span>
							{#if selected}
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 20 20"
									fill="currentColor"
									class="size-4 text-gray-600 dark:text-gray-300"
								>
									<path
										fill-rule="evenodd"
										d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z"
										clip-rule="evenodd"
									/>
								</svg>
							{/if}
						</svelte:fragment>
					</Select>
				</div>
			</div>

			<!-- 时间 -->
			<div class="flex items-center gap-3">
				<div class="w-20 text-sm font-medium text-gray-600 dark:text-gray-300 shrink-0">
					{$i18n.t('When')}
				</div>
				<div class="flex-1 min-w-0">
					<div class="flex items-center gap-1.5 flex-wrap text-gray-800 dark:text-gray-200">
						<input
							type="date"
							class="text-sm bg-gray-50 dark:bg-gray-850/60 hover:bg-gray-100 dark:hover:bg-gray-800 px-3 py-2 rounded-xl outline-hidden border border-transparent focus:border-gray-300 dark:focus:border-gray-700 transition disabled:opacity-60"
							bind:value={startDate}
							on:change={handleStartDateChange}
							disabled={readOnly}
						/>
						{#if !allDay}
							<input
								type="time"
								class="text-sm bg-gray-50 dark:bg-gray-850/60 hover:bg-gray-100 dark:hover:bg-gray-800 px-3 py-2 rounded-xl outline-hidden border border-transparent focus:border-gray-300 dark:focus:border-gray-700 transition disabled:opacity-60"
								bind:value={startTime}
								on:change={handleStartTimeChange}
								disabled={readOnly}
							/>
							<span class="text-gray-400 dark:text-gray-500 mx-0.5">→</span>
							<input
								type="time"
								class="text-sm bg-gray-50 dark:bg-gray-850/60 hover:bg-gray-100 dark:hover:bg-gray-800 px-3 py-2 rounded-xl outline-hidden border border-transparent focus:border-gray-300 dark:focus:border-gray-700 transition disabled:opacity-60"
								bind:value={endTime}
								min={endDate === startDate ? startTime : undefined}
								on:change={handleEndTimeChange}
								disabled={readOnly}
							/>
						{/if}
						<label
							class="flex items-center gap-1.5 cursor-pointer text-sm text-gray-600 dark:text-gray-300 ml-auto px-2 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800/40 transition"
						>
							<input
								type="checkbox"
								class="accent-gray-800 dark:accent-gray-200"
								bind:checked={allDay}
								disabled={readOnly}
							/>
							{$i18n.t('All day')}
						</label>
					</div>
				</div>
			</div>

			<!-- 地点 -->
			<div class="flex items-center gap-3">
				<div class="w-20 text-sm font-medium text-gray-600 dark:text-gray-300 shrink-0">
					{$i18n.t('Location')}
				</div>
				<div class="flex-1 min-w-0">
					<input
						class="w-full text-sm bg-gray-50 dark:bg-gray-850/60 hover:bg-gray-100 dark:hover:bg-gray-800 focus:bg-gray-100 dark:focus:bg-gray-800 outline-hidden text-gray-800 dark:text-gray-200 placeholder:text-gray-400 dark:placeholder:text-gray-600 px-3 py-2 rounded-xl border border-transparent focus:border-gray-300 dark:focus:border-gray-700 transition disabled:opacity-60"
						placeholder={$i18n.t('Add location')}
						bind:value={location}
						disabled={readOnly}
					/>
				</div>
			</div>

			<!-- 提醒 -->
			<div class="flex items-center gap-3">
				<div class="w-20 text-sm font-medium text-gray-600 dark:text-gray-300 shrink-0">
					{$i18n.t('Reminder')}
				</div>
				<div class="flex-1 min-w-0">
					<Select
						value={alertMinutes}
						items={alertItems}
						onChange={(v) => (alertMinutes = v)}
						triggerClass="w-full flex items-center justify-between gap-2 text-sm bg-gray-50 dark:bg-gray-850/60 hover:bg-gray-100 dark:hover:bg-gray-800 px-3 py-2 rounded-xl border border-transparent text-gray-800 dark:text-gray-200 transition disabled:cursor-not-allowed disabled:opacity-60"
						itemClass="flex w-full gap-2 items-center text-left px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
						align="start"
					>
						<svelte:fragment slot="trigger" let:selectedLabel let:open>
							<span class="truncate text-left flex-1">{selectedLabel}</span>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 20 20"
								fill="currentColor"
								class="size-4 text-gray-400 shrink-0 transition-transform {open
									? 'rotate-180'
									: ''}"
							>
								<path
									fill-rule="evenodd"
									d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.06l3.71-3.83a.75.75 0 1 1 1.08 1.04l-4.25 4.39a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z"
									clip-rule="evenodd"
								/>
							</svg>
						</svelte:fragment>
					</Select>
				</div>
			</div>

			<!-- 描述 -->
			<div class="flex items-start gap-3">
				<div class="w-20 text-sm font-medium text-gray-600 dark:text-gray-300 shrink-0 pt-2">
					{$i18n.t('Description')}
				</div>
				<div class="flex-1 min-w-0">
					<textarea
						class="w-full text-sm bg-gray-50 dark:bg-gray-850/60 hover:bg-gray-100 dark:hover:bg-gray-800 focus:bg-gray-100 dark:focus:bg-gray-800 outline-hidden text-gray-800 dark:text-gray-200 placeholder:text-gray-400 dark:placeholder:text-gray-600 resize-none min-h-[5rem] px-3 py-2 rounded-xl border border-transparent focus:border-gray-300 dark:focus:border-gray-700 transition disabled:opacity-60"
						placeholder={$i18n.t('Add description')}
						bind:value={description}
						rows="3"
						disabled={readOnly}
					></textarea>
				</div>
			</div>
		</div>

		<!-- Footer -->
		<div
			class="flex items-center justify-between px-4 pb-3.5 pt-2 gap-2 border-t border-gray-100 dark:border-gray-850 mt-2"
		>
			<div class="flex items-center gap-0.5 flex-1 min-w-0">
				{#if event && !isAutomation}
					<button
						class="px-3 py-2 text-xs font-medium text-rose-500 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20 rounded-xl transition"
						type="button"
						on:click={() => (showDeleteConfirmDialog = true)}
						disabled={loading}
					>
						{$i18n.t('Delete')}
					</button>
				{/if}
			</div>

			<div class="flex items-center gap-1.5 shrink-0">
				<button
					class="px-3 py-2 text-xs font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 transition"
					type="button"
					on:click={() => (show = false)}
				>
					{$i18n.t('Cancel')}
				</button>
				{#if !readOnly}
					<button
						class="px-3 py-2 text-xs font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-xl flex items-center gap-1.5 disabled:opacity-50 {loading
							? 'cursor-not-allowed'
							: ''}"
						on:click={submitHandler}
						type="button"
						disabled={loading}
					>
						{event ? $i18n.t('Save') : $i18n.t('Create')}
						{#if loading}
							<span class="shrink-0"><Spinner className="size-3" /></span>
						{/if}
					</button>
				{/if}
			</div>
		</div>
	</div>
</Modal>

<DeleteConfirmDialog
	bind:show={showDeleteConfirmDialog}
	title={$i18n.t('Delete Task')}
	message={$i18n.t('This action cannot be undone. Do you wish to continue?')}
	on:confirm={deleteHandler}
/>
