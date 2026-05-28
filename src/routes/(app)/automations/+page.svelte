<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';

	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { WEBUI_NAME, mobile, showSidebar, user, config, socket } from '$lib/stores';

	import {
		getAutomationItems,
		getAutomationById,
		toggleAutomationById,
		deleteAutomationById,
		type AutomationResponse
	} from '$lib/apis/automations';

	import AutomationModal from '$lib/components/AutomationModal.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import Select from '$lib/components/automations/_Select.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import Check from '$lib/components/icons/Check.svelte';

	const i18n = getContext('i18n');

	let loaded = false;
	let automations: AutomationResponse[] | null = null;
	let total: number | null = null;
	let loading = false;

	let showCreateModal = false;

	let showDeleteConfirm = false;
	let deleteTarget: AutomationResponse | null = null;

	let query = '';
	let statusFilter = 'all';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;

	let page = 1;

	$: if (loaded && query !== undefined) {
		loading = true;
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			page = 1;
			getAutomationList();
		}, 300);
	}

	$: if (loaded && page && statusFilter !== undefined) {
		getAutomationList();
	}

	const getAutomationList = async () => {
		if (!loaded) return;

		loading = true;
		try {
			const res = await getAutomationItems(localStorage.token, query, statusFilter, page).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);

			if (res) {
				automations = res.items;
				total = res.total;
			}
		} catch (err) {
			console.error(err);
		} finally {
			loading = false;
		}
	};

	const toggleHandler = async (automation: AutomationResponse) => {
		const res = await toggleAutomationById(localStorage.token, automation.id).catch((err) => {
			toast.error(`${err}`);
			return null;
		});
		if (res) {
			automations = (automations ?? []).map((a) => (a.id === res.id ? res : a));
		}
	};

	const deleteHandler = async (automation: AutomationResponse) => {
		const res = await deleteAutomationById(localStorage.token, automation.id).catch((err) => {
			toast.error(`${err}`);
			return null;
		});
		if (res) {
			toast.success($i18n.t(`Deleted {{name}}`, { name: automation.name }));
		}

		page = 1;
		getAutomationList();
	};

	const formatTime = (hour: number, minute: number): string => {
		return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
	};

	const parseRRuleParts = (line: string): Record<string, string> => {
		const parts: Record<string, string> = {};
		line.replace('RRULE:', '')
			.split(';')
			.forEach((p) => {
				const [k, v] = p.split('=');
				if (k && v) parts[k] = v;
			});
		return parts;
	};

	const DAY_KEYS = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'] as const;
	const DAY_ORDER: Record<string, number> = {
		MO: 0,
		TU: 1,
		WE: 2,
		TH: 3,
		FR: 4,
		SA: 5,
		SU: 6
	};

	const localizeDays = (raw: string): string => {
		const days = raw
			.split(',')
			.map((d) => d.trim().toUpperCase())
			.filter((d) => DAY_KEYS.includes(d as (typeof DAY_KEYS)[number]));
		if (!days.length) return '';
		days.sort((a, b) => (DAY_ORDER[a] ?? 99) - (DAY_ORDER[b] ?? 99));
		// Translation keys are title-cased ("Mo", "Tu", ...), not the RRULE upper-case codes.
		return days
			.map((d) => $i18n.t(d.charAt(0) + d.charAt(1).toLowerCase(), { context: 'day_of_week' }))
			.join(', ');
	};

	const formatRRule = (rrule: string): string => {
		if (rrule.includes('COUNT=1')) {
			const match = rrule.match(/DTSTART:(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})/);
			if (match) {
				const d = new Date(`${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}`);
				return `${$i18n.t('Once')} · ${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${formatTime(d.getHours(), d.getMinutes())}`;
			}
			return $i18n.t('Once');
		}

		// Collect all RRULE lines (DAILY multi-times are emitted as one RRULE per time).
		const rruleLines = rrule
			.split(/\r?\n/)
			.map((l) => l.trim())
			.filter((l) => l.startsWith('RRULE:'));

		if (rruleLines.length > 1) {
			const allDaily = rruleLines.every((l) => {
				const p = parseRRuleParts(l);
				return p.FREQ === 'DAILY' && !p.BYDAY && !p.BYMONTHDAY;
			});
			if (allDaily) {
				const times = rruleLines.map((l) => {
					const p = parseRRuleParts(l);
					const h = parseInt((p.BYHOUR || '0').split(',')[0]);
					const m = parseInt((p.BYMINUTE || '0').split(',')[0]);
					return { h, m, key: h * 60 + m };
				});
				const seen = new Set<number>();
				const sorted = times
					.filter((t) => {
						if (seen.has(t.key)) return false;
						seen.add(t.key);
						return true;
					})
					.sort((a, b) => a.key - b.key);
				const timeStr = sorted.map((t) => formatTime(t.h, t.m)).join(', ');
				return $i18n.t('Daily at {{time}}', { time: timeStr });
			}
		}

		const line = rruleLines[0] || rrule;
		const parts = parseRRuleParts(line);
		const freq = parts.FREQ || '';
		// BYHOUR / BYMINUTE may carry multiple values on a single line.
		const byHours = (parts.BYHOUR || '0').split(',').map((v) => parseInt(v));
		const byMinutes = (parts.BYMINUTE || '0').split(',').map((v) => parseInt(v));
		const hour = byHours[0];
		const minute = byMinutes[0];
		const iv = parseInt(parts.INTERVAL || '1');
		const time = formatTime(hour, minute);

		if (freq === 'MINUTELY')
			return iv === 1 ? $i18n.t('Every minute') : $i18n.t('Every {{count}} minutes', { count: iv });
		if (freq === 'HOURLY')
			return iv === 1 ? $i18n.t('Hourly') : $i18n.t('Every {{count}} hours', { count: iv });
		if (freq === 'DAILY') {
			// Legacy single-line multi-times: BYHOUR=9,18 etc.
			if (byHours.length > 1 || byMinutes.length > 1) {
				const slots = new Set<number>();
				const list: { h: number; m: number; key: number }[] = [];
				for (const h of byHours) {
					for (const m of byMinutes) {
						const key = h * 60 + m;
						if (slots.has(key)) continue;
						slots.add(key);
						list.push({ h, m, key });
					}
				}
				list.sort((a, b) => a.key - b.key);
				const timeStr = list.map((t) => formatTime(t.h, t.m)).join(', ');
				return $i18n.t('Daily at {{time}}', { time: timeStr });
			}
			return $i18n.t('Daily at {{time}}', { time });
		}
		if (freq === 'WEEKLY') {
			const days = localizeDays(parts.BYDAY || '');
			return days ? `${days} · ${time}` : $i18n.t('Weekly at {{time}}', { time });
		}
		if (freq === 'MONTHLY')
			return $i18n.t('Monthly on day {{day}} at {{time}}', {
				day: parts.BYMONTHDAY || '1',
				time
			});
		return rrule;
	};

	// Real-time refresh: backend emits `automation:result` after every run.
	// Refresh just the affected row so we keep pagination/scroll intact and
	// avoid the flicker of a full list reload.
	const onAutomationResult = async (data: { automation_id?: string }) => {
		if (!data?.automation_id || !automations) return;
		if (!automations.some((a) => a.id === data.automation_id)) return;

		const fresh = await getAutomationById(localStorage.token, data.automation_id).catch(
			() => null
		);
		if (!fresh) return;

		automations = automations.map((a) => (a.id === fresh.id ? fresh : a));
	};

	onMount(async () => {
		if (
			!$config?.features?.enable_automations ||
			($user?.role !== 'admin' && !($user?.permissions?.features?.automations ?? false))
		) {
			goto('/');
			return;
		}

		loaded = true;
		await getAutomationList();

		$socket?.on('automation:result', onAutomationResult);

		return () => {
			clearTimeout(searchDebounceTimer);
		};
	});

	onDestroy(() => {
		clearTimeout(searchDebounceTimer);
		$socket?.off('automation:result', onAutomationResult);
	});
</script>

<svelte:head>
	<title>{$i18n.t('Automations')} • {$WEBUI_NAME}</title>
</svelte:head>

<DeleteConfirmDialog
	bind:show={showDeleteConfirm}
	title={$i18n.t('Delete automation?')}
	on:confirm={() => {
		if (deleteTarget) deleteHandler(deleteTarget);
	}}
>
	<div class="text-sm text-gray-500 truncate">
		{$i18n.t('This will delete')} <span class="font-medium">{deleteTarget?.name}</span>.
	</div>
</DeleteConfirmDialog>

<AutomationModal
	bind:show={showCreateModal}
	automation={null}
	on:save={(e) => {
		getAutomationList();
		if (e.detail?.id) {
			goto(`/automations/${e.detail.id}`);
		}
	}}
/>

<div class="flex flex-col w-full h-full max-h-full max-w-full">
	<div class="flex-1 min-h-0 flex flex-col overflow-hidden">
		{#if loaded}
			<div class="flex-1 min-h-0 flex flex-col pb-3 px-3 md:px-[18px] pt-2">
				<!-- Header -->
				<div class="flex flex-col gap-2 px-1 mt-1.5 mb-4 shrink-0">
					<div class="flex justify-between items-center">
						<div class="flex items-center gap-3 shrink-0">
							{#if $mobile}
								<Tooltip
									content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
								>
									<button
										id="sidebar-toggle-button"
										class="cursor-pointer flex rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition"
										on:click={() => {
											showSidebar.set(!$showSidebar);
										}}
									>
										<div class="self-center p-1.5">
											<SidebarIcon />
										</div>
									</button>
								</Tooltip>
							{/if}
							<div
								class="flex items-center justify-center w-9 h-9 rounded-xl bg-sky-500/10 dark:bg-sky-500/15"
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="1.5"
									stroke="currentColor"
									class="size-5 text-sky-600 dark:text-sky-400"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
									/>
								</svg>
							</div>
							<div>
								<div class="text-xl font-semibold">{$i18n.t('Automations')}</div>
								{#if total !== null}
									<div class="text-xs text-gray-500 dark:text-gray-400">
										{total} {$i18n.t('items')}
									</div>
								{/if}
							</div>
						</div>

						<div class="flex w-full justify-end gap-1.5">
							<button
								class="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
								on:click={() => {
									showCreateModal = true;
								}}
							>
								<Plus className="size-3.5" strokeWidth="2.5" />
								<div class="hidden md:block text-xs">
									{$i18n.t('New Automation')}
								</div>
							</button>
						</div>
					</div>
				</div>

				<!-- Card -->
				<div
					class="py-2.5 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm flex-1 min-h-0 flex flex-col overflow-hidden"
				>
					<!-- Search -->
					<div class="flex w-full space-x-2 py-0.5 px-4 pb-2.5 shrink-0">
						<div
							class="flex flex-1 items-center bg-gray-50 dark:bg-gray-850 rounded-xl px-3 py-1.5 transition focus-within:ring-2 focus-within:ring-gray-300/50 dark:focus-within:ring-gray-600/50 focus-within:bg-white dark:focus-within:bg-gray-900"
						>
							<Search className="size-3.5 text-gray-400 shrink-0" />
							<input
								class="w-full text-sm py-0.5 pl-2 outline-hidden bg-transparent placeholder:text-gray-400"
								bind:value={query}
								aria-label={$i18n.t('Search Automations')}
								placeholder={$i18n.t('Search Automations')}
								maxlength="500"
							/>
							{#if query}
								<button
									class="p-0.5 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition ml-1"
									aria-label={$i18n.t('Clear search')}
									on:click={() => {
										query = '';
									}}
								>
									<XMark className="size-3" strokeWidth="2" />
								</button>
							{/if}
						</div>
					</div>

					<!-- Filter -->
					<div class="px-3.5 flex w-full bg-transparent overflow-x-auto scrollbar-none shrink-0">
						<div
							class="flex gap-0.5 w-fit text-center text-sm rounded-full bg-transparent px-1 whitespace-nowrap"
						>
							<Select
								bind:value={statusFilter}
								items={[
									{ value: 'all', label: $i18n.t('All') },
									{ value: 'active', label: $i18n.t('Enabled') },
									{ value: 'paused', label: $i18n.t('Paused') }
								]}
								onChange={() => {
									page = 1;
								}}
								triggerClass="relative w-full flex items-center gap-0.5 px-2.5 py-1.5 bg-gray-50 dark:bg-gray-850 rounded-xl"
							>
								<svelte:fragment slot="trigger" let:selectedLabel>
									<span
										class="inline-flex h-input px-0.5 w-full outline-hidden bg-transparent truncate placeholder-gray-400 focus:outline-hidden"
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
						</div>
					</div>

					<!-- List -->
					{#if automations === null || loading}
						<div class="flex-1 min-h-0 w-full flex justify-center items-center py-16">
							<Spinner className="size-5" />
						</div>
					{:else if (automations ?? []).length === 0}
						<div class="flex-1 min-h-0 w-full flex flex-col justify-center items-center py-20">
							<div class="max-w-sm text-center">
								<div
									class="flex items-center justify-center w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-800 mx-auto mb-4"
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										fill="none"
										viewBox="0 0 24 24"
										stroke-width="1.5"
										stroke="currentColor"
										class="size-8 text-gray-400"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
										/>
									</svg>
								</div>
							<div class="text-base font-semibold {query ? 'mb-1.5' : ''}">
								{query ? $i18n.t('No results found') : $i18n.t('No automations found')}
							</div>
							{#if query}
								<div class="text-gray-500 text-xs">
									{$i18n.t(
										'Try adjusting your search or filter to find what you are looking for.'
									)}
								</div>
							{/if}
							</div>
						</div>
					{:else}
						<div class="flex-1 min-h-0 overflow-y-auto">
							<div class="gap-2.5 grid mt-2 px-3 pb-2">
							{#each automations as automation (automation.id)}
								<a
									class="group flex text-left w-full px-4 py-3.5 hover:bg-gray-50 dark:hover:bg-gray-850/60 transition-all duration-200 rounded-xl border border-transparent hover:border-gray-200/60 dark:hover:border-gray-700/40 hover:shadow-sm"
									href={`/automations/${automation.id}`}
								>
									<div class="flex items-start gap-3 flex-1 min-w-0">
										<div
											class="flex items-center justify-center w-10 h-10 rounded-lg shrink-0 mt-0.5 transition-colors {automation.is_active
												? 'bg-sky-50 dark:bg-sky-500/10 group-hover:bg-sky-100 dark:group-hover:bg-sky-500/20'
												: 'bg-gray-100 dark:bg-gray-800 group-hover:bg-gray-200 dark:group-hover:bg-gray-700'}"
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												fill="none"
												viewBox="0 0 24 24"
												stroke-width="1.5"
												stroke="currentColor"
												class="size-5 {automation.is_active
													? 'text-sky-600 dark:text-sky-400'
													: 'text-gray-400 dark:text-gray-500'}"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
												/>
											</svg>
										</div>
										<div class="flex-1 min-w-0">
											<div class="flex items-center gap-2 mb-1 min-w-0">
												<div class="font-semibold text-sm line-clamp-1">{automation.name}</div>
											</div>
											<div
												class="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400"
											>
												<span class="shrink-0">{formatRRule(automation.data.rrule)}</span>
												<span class="text-gray-300 dark:text-gray-600">·</span>
												<span
													class="inline-flex items-center gap-1 shrink-0 {automation.is_active
														? 'text-emerald-600 dark:text-emerald-400'
														: 'text-gray-500 dark:text-gray-400'}"
												>
												<span
													class="inline-block size-1.5 rounded-full {automation.is_active
														? 'bg-emerald-500'
														: 'bg-gray-400'}"
												></span>
												{automation.is_active ? $i18n.t('Enabled') : $i18n.t('Paused')}
												</span>
											</div>
										</div>
									</div>

									<div class="flex flex-row gap-0.5 self-center shrink-0">
										<Tooltip content={$i18n.t('Delete')}>
											<button
												class="self-center w-fit text-sm p-1.5 text-gray-500 hover:text-red-600 dark:text-gray-300 dark:hover:text-red-400 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
												type="button"
												aria-label={$i18n.t('Delete')}
												on:click|preventDefault|stopPropagation={() => {
													deleteTarget = automation;
													showDeleteConfirm = true;
												}}
											>
												<GarbageBin className="size-4" strokeWidth="2" />
											</button>
										</Tooltip>

										<button
											on:click|preventDefault|stopPropagation
											class="self-center px-1"
										>
											<Tooltip
												content={automation.is_active ? $i18n.t('Enabled') : $i18n.t('Disabled')}
											>
												<Switch
													bind:state={automation.is_active}
													on:change={() => {
														toggleHandler(automation);
													}}
												/>
											</Tooltip>
										</button>
									</div>
								</a>
							{/each}
							</div>

							{#if total > 30}
								<div class="flex justify-center mt-4 mb-2">
									<Pagination bind:page count={total} perPage={30} />
								</div>
							{/if}
						</div>
					{/if}
				</div>
			</div>
		{:else}
			<div class="w-full h-full flex justify-center items-center">
				<Spinner className="size-5" />
			</div>
		{/if}
	</div>
</div>
