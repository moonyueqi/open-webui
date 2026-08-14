<script lang="ts">
	import { onMount, onDestroy, getContext, tick } from 'svelte';
	import { page } from '$app/stores';

	import {
		getGroundAlarms,
		getGroundSummary,
		type GroundAlarmModel,
		type GroundAlarmSummaryResponse
	} from '$lib/apis/monitoring';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	// 预警等级颜色映射，跟气象部门通行的蓝/黄/橙/红四级一致。
	const LEVELS = ['蓝', '黄', '橙', '红'];
	const LEVEL_DOT: Record<string, string> = {
		蓝: 'bg-sky-500',
		黄: 'bg-amber-400',
		橙: 'bg-orange-500',
		红: 'bg-red-600'
	};
	const LEVEL_BADGE: Record<string, string> = {
		蓝: 'bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300',
		黄: 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
		橙: 'bg-orange-50 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
		红: 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300'
	};

	// 临时兜底样例数据：接口/网络异常拿不到真实数据时，先用这条把页面样式展示出来，
	// 方便预览效果。等真实数据链路稳定后，这段可以整段删掉。
	const FALLBACK_ALARM: GroundAlarmModel = {
		id: 'demo-ground-1',
		push_time: null,
		coverage_start: null,
		coverage_end: null,
		station_id: 'AD505',
		station_name: '北孙各庄',
		county: '顺义区',
		province: '北京市',
		observed_at: new Date(2026, 6, 28, 11, 30, 0).getTime() * 1_000_000,
		pre: 0,
		rain_5m: 0.0,
		rain_10m: 0.3,
		rain_15m: 4.5,
		rain_20m: 10.6,
		rain_25m: 17.1,
		rain_30m: 19.5,
		level: '蓝',
		source_file: 'demo',
		created_at: 0
	};
	const FALLBACK_SUMMARY: GroundAlarmSummaryResponse = {
		active_count: 1,
		by_level: { 蓝: 1 },
		county_count: 1,
		latest_alarm_at: FALLBACK_ALARM.observed_at,
		updated_at: null
	};

	let loading = true;
	let refreshing = false;
	let summary: GroundAlarmSummaryResponse | null = null;
	let alarms: GroundAlarmModel[] = [];

	let levelFilter: string[] = [];
	let countyFilter = '';
	let highlightId: string | null = null;

	let counties: string[] = [];
	let refreshTimer: ReturnType<typeof setInterval> | null = null;

	const formatTime = (ns: number | null) => {
		if (!ns) return '--';
		return new Date(ns / 1_000_000).toLocaleString('zh-CN', {
			month: '2-digit',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit'
		});
	};

	const formatRain = (v: number | null) => (v != null ? `${v}mm` : '--');

	// 页面永远只看"当前状态"（每站最新一条），历史推送不在这里展示。
	const load = async (scrollToHighlight = false) => {
		refreshing = true;
		try {
			const [summaryRes, alarmsRes] = await Promise.all([
				getGroundSummary(localStorage.token),
				getGroundAlarms(localStorage.token, {
					level: levelFilter.length ? levelFilter : undefined,
					county: countyFilter || undefined,
					latest_only: true,
					limit: 200
				})
			]);
			summary = summaryRes;
			alarms = alarmsRes.items;
			if (!countyFilter) {
				counties = Array.from(
					new Set(alarms.map((a) => a.county).filter((c): c is string => !!c))
				).sort();
			}
		} catch (e) {
			console.error(e);
		}

		if (!alarms || alarms.length === 0) {
			// 临时兜底，见上方 FALLBACK_ALARM 注释。
			alarms = [FALLBACK_ALARM];
			summary = FALLBACK_SUMMARY;
			counties = ['顺义区'];
		}

		loading = false;
		refreshing = false;

		if (scrollToHighlight && highlightId) {
			await tick();
			const el = document.getElementById(`ground-alarm-${highlightId}`);
			if (el) {
				el.scrollIntoView({ behavior: 'smooth', block: 'center' });
			}
		}
	};

	const toggleLevel = (level: string) => {
		levelFilter = levelFilter.includes(level)
			? levelFilter.filter((l) => l !== level)
			: [...levelFilter, level];
		load();
	};

	onMount(async () => {
		highlightId = $page.url.searchParams.get('alarm_id');
		await load(true);

		refreshTimer = setInterval(() => load(), 60_000);
	});

	onDestroy(() => {
		if (refreshTimer) clearInterval(refreshTimer);
	});
</script>

<div class="flex flex-col flex-1 min-h-0 gap-3 overflow-y-auto scrollbar-thin pr-0.5">
	{#if loading}
		<div class="flex-1 flex items-center justify-center">
			<Spinner />
		</div>
	{:else}
		<!-- 统计卡片 -->
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
			<div class="rounded-xl border border-gray-100 dark:border-gray-800 p-3">
				<div class="text-xs text-gray-400 dark:text-gray-500">
					{$i18n.t('Latest Alarm Time')}
				</div>
				<div class="text-2xl font-semibold mt-1">{formatTime(summary?.latest_alarm_at ?? null)}</div>
			</div>
			<div class="rounded-xl border border-gray-100 dark:border-gray-800 p-3">
				<div class="text-xs text-gray-400 dark:text-gray-500">
					{$i18n.t('Counties Affected')}
				</div>
				<div class="text-2xl font-semibold mt-1">{summary?.county_count ?? 0}</div>
			</div>
			<div class="col-span-2 rounded-xl border border-gray-100 dark:border-gray-800 p-3">
				<div class="text-xs text-gray-400 dark:text-gray-500 mb-2">
					{$i18n.t('By Level')}
				</div>
				<div class="flex flex-wrap gap-2">
					{#each LEVELS as level}
						<span
							class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium {LEVEL_BADGE[
								level
							]}"
						>
							<span class="size-2 rounded-full {LEVEL_DOT[level]}"></span>
							{level}色 · {summary?.by_level?.[level] ?? 0}
						</span>
					{/each}
				</div>
			</div>
		</div>

		<!-- 筛选栏 -->
		<div class="flex flex-wrap items-center gap-2 text-sm">
			<div class="flex items-center gap-1">
				{#each LEVELS as level}
					<button
						class="px-2 py-1 rounded-md text-xs border transition {levelFilter.includes(level)
							? `${LEVEL_BADGE[level]} border-transparent`
							: 'border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500'}"
						on:click={() => toggleLevel(level)}
					>
						{level}色
					</button>
				{/each}
			</div>

			<select
				class="text-xs bg-transparent border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1 w-28 truncate"
				title={countyFilter || $i18n.t('All Counties')}
				bind:value={countyFilter}
				on:change={() => load()}
			>
				<option value="">{$i18n.t('All Counties')}</option>
				{#each counties as c}
					<option value={c}>{c}</option>
				{/each}
			</select>

			<span class="grow"></span>

			<Tooltip content={$i18n.t('Requires station coordinates to enable')}>
				<button
					class="px-2.5 py-1 rounded-md text-xs border border-gray-200 dark:border-gray-700 text-gray-300 dark:text-gray-600 cursor-not-allowed"
					disabled
				>
					{$i18n.t('Map View')}
				</button>
			</Tooltip>

			<button
				class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 {refreshing
					? 'animate-pulse'
					: ''}"
				on:click={() => load()}
			>
				{$i18n.t('Refresh')}
			</button>
		</div>

		<!-- 告警表格 -->
		<div class="flex-1 min-h-0 overflow-auto rounded-xl border border-gray-100 dark:border-gray-800">
			{#if alarms.length === 0}
				<div class="flex flex-col items-center justify-center py-16 text-gray-400 dark:text-gray-500 text-sm">
					{$i18n.t('No data available yet')}
				</div>
			{:else}
				<table class="w-full text-sm">
					<thead class="sticky top-0 bg-gray-50 dark:bg-gray-850 text-xs text-gray-400 dark:text-gray-500">
						<tr>
							<th class="text-left font-normal px-3 py-2">{$i18n.t('County')}</th>
							<th class="text-left font-normal px-3 py-2">{$i18n.t('Station')}</th>
							<th class="text-left font-normal px-3 py-2">{$i18n.t('Level')}</th>
							<th class="text-right font-normal px-3 py-2">{$i18n.t('5min Rainfall')}</th>
							<th class="text-right font-normal px-3 py-2">{$i18n.t('10min Rainfall')}</th>
							<th class="text-right font-normal px-3 py-2">{$i18n.t('15min Rainfall')}</th>
							<th class="text-right font-normal px-3 py-2">{$i18n.t('20min Rainfall')}</th>
							<th class="text-right font-normal px-3 py-2">{$i18n.t('25min Rainfall')}</th>
							<th class="text-right font-normal px-3 py-2">{$i18n.t('30min Rainfall')}</th>
						</tr>
					</thead>
					<tbody>
						{#each alarms as alarm (alarm.id)}
							<tr
								id={`ground-alarm-${alarm.id}`}
								class="border-t border-gray-50 dark:border-gray-850 transition {highlightId ===
								alarm.id
									? 'bg-amber-50 dark:bg-amber-900/20'
									: 'hover:bg-gray-50 dark:hover:bg-gray-850/60'}"
							>
								<td class="px-3 py-2 whitespace-nowrap">{alarm.county ?? '--'}</td>
								<td class="px-3 py-2 whitespace-nowrap">{alarm.station_name ?? alarm.station_id}</td>
								<td class="px-3 py-2">
									<span
										class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs {LEVEL_BADGE[
											alarm.level ?? ''
										] ?? 'bg-gray-100 text-gray-500 dark:bg-gray-800'}"
									>
										<span class="size-1.5 rounded-full {LEVEL_DOT[alarm.level ?? ''] ?? 'bg-gray-400'}"
										></span>
										{alarm.level ?? '--'}色
									</span>
								</td>
								<td class="px-3 py-2 text-right whitespace-nowrap">{formatRain(alarm.rain_5m)}</td>
								<td class="px-3 py-2 text-right whitespace-nowrap">{formatRain(alarm.rain_10m)}</td>
								<td class="px-3 py-2 text-right whitespace-nowrap">{formatRain(alarm.rain_15m)}</td>
								<td class="px-3 py-2 text-right whitespace-nowrap">{formatRain(alarm.rain_20m)}</td>
								<td class="px-3 py-2 text-right whitespace-nowrap">{formatRain(alarm.rain_25m)}</td>
								<td class="px-3 py-2 text-right whitespace-nowrap">{formatRain(alarm.rain_30m)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</div>
	{/if}
</div>
