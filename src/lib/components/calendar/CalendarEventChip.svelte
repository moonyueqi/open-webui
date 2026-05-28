<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import type { CalendarEventModel } from '$lib/apis/calendar';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	export let event: CalendarEventModel;
	export let calendarColor: string | null = null;

	const dispatch = createEventDispatcher();

	$: dotColor = event.color || calendarColor || '#3b82f6';
	$: isAutomation = !!event.meta?.automation_id;

	function formatTime(ns: number): string {
		const d = new Date(ns / 1_000_000);
		return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
	}
</script>

<Tooltip content="{event.title}{event.location ? ` · ${event.location}` : ''}">
	<button
		class="group/chip w-full text-left text-[11px] flex items-center gap-1 py-[2px] px-1.5 rounded-md transition truncate
			{isAutomation ? 'opacity-80' : ''}
			hover:shadow-sm"
		style="background-color: {dotColor}1a;"
		on:click|stopPropagation={() => dispatch('click', event)}
	>
		<span
			class="shrink-0 size-[7px] rounded-full"
			style="background-color: {dotColor};"
		></span>
		{#if isAutomation}
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 24 24"
				fill="currentColor"
				class="size-2.5 shrink-0 text-gray-500 dark:text-gray-400"
				aria-hidden="true"
			>
				<path
					fill-rule="evenodd"
					d="M14.615 1.595a.75.75 0 0 1 .359.852L12.982 9.75h7.268a.75.75 0 0 1 .548 1.262l-10.5 11.25a.75.75 0 0 1-1.272-.71l1.992-7.302H3.75a.75.75 0 0 1-.548-1.262l10.5-11.25a.75.75 0 0 1 .913-.143Z"
					clip-rule="evenodd"
				/>
			</svg>
		{/if}
		<span class="truncate flex-1 text-gray-800 dark:text-gray-100 font-medium">
			{#if !event.all_day}<span class="text-gray-500 dark:text-gray-400 mr-1 font-normal"
					>{formatTime(event.start_at)}</span
				>{/if}{event.title}
		</span>
	</button>
</Tooltip>
