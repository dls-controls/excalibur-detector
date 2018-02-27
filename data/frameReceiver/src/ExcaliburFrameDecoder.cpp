/*
 * ExcaliburFrameDecoder.cpp
 *
 *  Created on: Jan 16th, 2017
 *      Author: Tim Nicholls, STFC Application Engineering Group
 */

#include "ExcaliburFrameDecoder.h"
#include "gettime.h"
#include <iostream>
#include <iomanip>
#include <sstream>
#include <string>
#include <arpa/inet.h>
#include <boost/algorithm/string.hpp>

using namespace FrameReceiver;

const std::string ExcaliburFrameDecoder::asic_bit_depth_str_[Excalibur::num_bit_depths] =
    {"1-bit", "6-bit", "12-bit", "24-bit"};

#define MAX_IGNORED_PACKET_REPORTS 10

static void* last_buffer_addr = NULL;
static bool first_tp_found = false;

//! Constructor for ExcaliburFrameDecoder
//!
//! This constructor sets up the decoder, setting default values of frame tracking information
//! and allocating buffers for packet header, dropped frames and scratched packets
//!
ExcaliburFrameDecoder::ExcaliburFrameDecoder() :
    FrameDecoderUDP(),
    asic_counter_bit_depth_(Excalibur::bitDepth12),
    current_frame_seen_(Excalibur::default_frame_number),
    current_frame_buffer_id_(Excalibur::default_frame_number),
    current_frame_buffer_(0),
    current_frame_header_(0),
    num_active_fems_(0),
    dropping_frame_data_(false),
    packets_ignored_(0),
    has_subframe_trailer_(true),
    last_shadow_frame_number_(0),
    current_shadow_frame_number_(0)
{

  // Allocate buffers for packet header, dropped frames and scratched packets
  current_packet_header_.reset(new uint8_t[sizeof(Excalibur::PacketHeader)]);
  dropped_frame_buffer_.reset(new uint8_t[Excalibur::max_frame_size()]);
  ignored_packet_buffer_.reset(new uint8_t[Excalibur::primary_packet_size]);

}

//! Destructor for ExcaliburFrameDecoder
//!
ExcaliburFrameDecoder::~ExcaliburFrameDecoder()
{
}

//! Initialise the frame decoder.
//!
//! This method initialises the decoder based on a configuration message passed by the
//! application controller. Parameters found in the decoder configuraiton are parsed and stored
//! in the decoder as appropriate.
//!
//! \param[in] logger - pointer to the message logger
//! \param[in] config_msg - configuration message
//!
void ExcaliburFrameDecoder::init(LoggerPtr& logger, OdinData::IpcMessage& config_msg)
{

  // Pass the configuratin message to the base class decoder
  FrameDecoder::init(logger, config_msg);

  LOG4CXX_DEBUG_LEVEL(2, logger_, "Got decoder config message: " << config_msg.encode());

  // Extract the FEM to port map from the config message and pass to the parser. If no map is
  // present, use the default. If the map cannot be parsed correctly, thrown an exception to signal
  // an error to the app controller. Set the current number of active FEMs based on the output
  // of the map parsing.
  std::string fem_port_map_config_str;
  if (config_msg.has_param("fem_port_map"))
  {
      LOG4CXX_DEBUG_LEVEL(1, logger_, "Parsing FEM to port map found in config: "
                          << config_msg.get_param<std::string>("fem_port_map"));
      fem_port_map_config_str = config_msg.get_param<std::string>("fem_port_map");
  }
  else
  {
      LOG4CXX_DEBUG_LEVEL(1,logger_, "No FEM to port map found in config, using default: "
                          << default_fem_port_map);
      fem_port_map_config_str = default_fem_port_map;
  }

  num_active_fems_ = parse_fem_port_map(fem_port_map_config_str);
  if (num_active_fems_)  {
      LOG4CXX_DEBUG_LEVEL(1, logger_, "Parsed " << num_active_fems_
                          << " entries from port map configuration");
  }
  else
  {
      throw OdinData::OdinDataException("Failed to parse FEM to port map entries from configuration");
  }

  // Extract the ASIC counter bit depth from the config message
  if (config_msg.has_param("bitdepth"))
  {
    std::string bit_depth_str = config_msg.get_param<std::string>("bitdepth");

    Excalibur::AsicCounterBitDepth bit_depth =
        parse_bit_depth(bit_depth_str);

    if (bit_depth == Excalibur::bitDepthUnknown)
    {
      LOG4CXX_ERROR(logger_, "Unknown bit depth configuration parameter specified: "
                    << bit_depth_str << ", defaulting to "
                    << asic_bit_depth_str_[asic_counter_bit_depth_]);
    }
    else
    {
      asic_counter_bit_depth_ = bit_depth;
    }
  }
  LOG4CXX_DEBUG_LEVEL(1, logger_, "Setting ASIC counter bit depth to "
      << asic_bit_depth_str_[asic_counter_bit_depth_]);

  // Determine if this readout mode has a subframe trailer
  if (asic_counter_bit_depth_ == Excalibur::bitDepth1)
  {
    has_subframe_trailer_ = false;
  }
  else
  {
    has_subframe_trailer_ = true;
  }
  // Reset shadow frame counter
  last_shadow_frame_number_ = 0;

  // Print a packet logger header to the appropriate logger if enabled
  if (enable_packet_logging_)
  {
    LOG4CXX_INFO(packet_logger_, "PktHdr: SourceAddress");
    LOG4CXX_INFO(packet_logger_, "PktHdr: |               SourcePort");
    LOG4CXX_INFO(packet_logger_, "PktHdr: |               |     DestinationPort");
    LOG4CXX_INFO(packet_logger_, "PktHdr: |               |     |      SubframeCounter  [4 Bytes]");
    LOG4CXX_INFO(packet_logger_,
        "PktHdr: |               |     |      |           PacketCounter&Flags [4 Bytes]");
    LOG4CXX_INFO(packet_logger_, "PktHdr: |               |     |      |           |");
    LOG4CXX_INFO(packet_logger_, "PktHdr: |-------------- |---- |----  |---------- |----------");
  }

  // Reset the scratched packet counter
  packets_ignored_ = 0;
}

const size_t ExcaliburFrameDecoder::get_frame_buffer_size(void) const
{
  size_t frame_buffer_size = get_frame_header_size() +
      (Excalibur::subframe_size(asic_counter_bit_depth_) * Excalibur::num_subframes * num_active_fems_);
  return frame_buffer_size;
}

const size_t ExcaliburFrameDecoder::get_frame_header_size(void) const
{
  return sizeof(Excalibur::FrameHeader);
}

const size_t ExcaliburFrameDecoder::get_packet_header_size(void) const
{
  return sizeof(Excalibur::PacketHeader);
}

void*
ExcaliburFrameDecoder::get_packet_header_buffer(void)
{
  return current_packet_header_.get();
}

void ExcaliburFrameDecoder::process_packet_header(size_t bytes_received, int port,
    struct sockaddr_in* from_addr)
{
  // Dump raw header if packet logging enabled
  if (enable_packet_logging_)
  {
    std::stringstream ss;
    uint8_t* hdr_ptr = reinterpret_cast<uint8_t*>(current_packet_header_.get ());
    ss << "PktHdr: " << std::setw (15) << std::left << inet_ntoa (from_addr->sin_addr)
        << std::right << " " << std::setw (5) << ntohs (from_addr->sin_port) << " " << std::setw(5)
        << port << std::hex;

    for (unsigned int hdr_byte = 0; hdr_byte < sizeof(Excalibur::PacketHeader); hdr_byte++)
    {
      if (hdr_byte % 8 == 0)
      {
        ss << "  ";
      }
      ss << std::setw (2) << std::setfill ('0') << (unsigned int) *hdr_ptr << " ";
      hdr_ptr++;
    }
    ss << std::dec;
    LOG4CXX_INFO(packet_logger_, ss.str ());
  }

  // Resolve the FEM index from the port the packet arrived on
  if (fem_port_map_.count(port)) {
    current_packet_fem_map_ =  fem_port_map_[port];

  }
  else
  {
    current_packet_fem_map_ = ExcaliburDecoderFemMapEntry(ILLEGAL_FEM_IDX, ILLEGAL_FEM_IDX);
    packets_ignored_++;
    if (packets_ignored_ < MAX_IGNORED_PACKET_REPORTS)
    {
      LOG4CXX_WARN(logger_, "Ignoring packet received on port " << port << " for unknown FEM idx");
    }
    else if (packets_ignored_ == MAX_IGNORED_PACKET_REPORTS)
    {
      LOG4CXX_WARN(logger_, "Reporting limit for ignored packets reached, suppressing further messages");
    }
  }

  // Extract fields from packet header
  uint32_t subframe_counter = get_subframe_counter ();
  uint32_t packet_number = get_packet_number ();
  bool start_of_frame_marker = get_start_of_frame_marker ();
  bool end_of_frame_marker = get_end_of_frame_marker ();

  uint32_t subframe_idx = subframe_counter % 2;
  int frame = static_cast<int> (subframe_counter / 2);

  LOG4CXX_DEBUG_LEVEL(3, logger_, "Got packet header:" << " packet: " << packet_number
      << " subframe ctr: " << subframe_counter
      << " idx:" << subframe_idx << " SOF: " << (int) start_of_frame_marker
      << " EOF: " << (int) end_of_frame_marker
      << " port: " << port << " fem idx: " << current_packet_fem_map_.fem_idx_
  );

  // Only handle the packet header and frame logic further is this packet is not being ignored
  if (current_packet_fem_map_.fem_idx_ != ILLEGAL_FEM_IDX)
  {
    if (frame != current_frame_seen_)
    {
      current_frame_seen_ = frame;

      if (frame_buffer_map_.count(current_frame_seen_) == 0)
      {
        if (empty_buffer_queue_.empty())
        {
          current_frame_buffer_ = dropped_frame_buffer_.get();

          if (!dropping_frame_data_)
          {
            LOG4CXX_ERROR(logger_, "First packet from frame " << current_frame_seen_
                << " detected but no free buffers available. Dropping packet data for this frame");
            dropping_frame_data_ = true;
          }
        }
        else
        {

          current_frame_buffer_id_ = empty_buffer_queue_.front();
          empty_buffer_queue_.pop();
          frame_buffer_map_[current_frame_seen_] = current_frame_buffer_id_;
          current_frame_buffer_ = buffer_manager_->get_buffer_address(current_frame_buffer_id_);

          if (!dropping_frame_data_)
          {
            LOG4CXX_DEBUG_LEVEL(2, logger_, "First packet from frame " << current_frame_seen_
                << " detected, allocating frame buffer ID " << current_frame_buffer_id_);
          }
          else
          {
            dropping_frame_data_ = false;
            LOG4CXX_DEBUG_LEVEL(2, logger_, "Free buffer now available for frame "
                << current_frame_seen_ << ", allocating frame buffer ID "
                << current_frame_buffer_id_);
          }
        }

        // Initialise frame header
        current_frame_header_ = reinterpret_cast<Excalibur::FrameHeader*>(current_frame_buffer_);
        initialise_frame_header(current_frame_header_);

        // Track shadow frame counter for the current frame
        current_shadow_frame_number_ = last_shadow_frame_number_++;
        shadow_frame_counter_map[current_frame_seen_] = current_shadow_frame_number_;

      }
      else
      {
        current_frame_buffer_id_ = frame_buffer_map_[current_frame_seen_];
        current_frame_buffer_ = buffer_manager_->get_buffer_address(current_frame_buffer_id_);
        current_frame_header_ = reinterpret_cast<Excalibur::FrameHeader*>(current_frame_buffer_);
        current_shadow_frame_number_ = shadow_frame_counter_map[current_frame_seen_];
      }

    }

    Excalibur::FemReceiveState* fem_rx_state =
        &(current_frame_header_->fem_rx_state[current_packet_fem_map_.buf_idx_]);

    // If SOF or EOF markers seen in packet header, increment appropriate field in frame header
    if (start_of_frame_marker)
    {
      (fem_rx_state->sof_marker_count)++;
      (current_frame_header_->total_sof_marker_count)++;
    }
    if (end_of_frame_marker)
    {
      (fem_rx_state->sof_marker_count)++;
      (current_frame_header_->total_eof_marker_count)++;
    }

    // Update packet_number state map in frame header
    fem_rx_state->packet_state[subframe_idx][packet_number] = 1;
  }

}

//! Initialise a frame header
//!
//! This method initialises the frame header specifed by the pointer argument, setting
//! fields to their default values, clearing packet counters and setting the active FEM
//! fields as appropriate.
//!
//! \param[in] - header_ptr - pointer to frame header to initialise.
//!
void ExcaliburFrameDecoder::initialise_frame_header(Excalibur::FrameHeader* header_ptr)
{

  // Initialise the frame number to -1 so we can pick this up from the first
  // subframe trailer seen in the packet stream
  header_ptr->frame_number = Excalibur::default_frame_number;

  header_ptr->frame_state = FrameDecoder::FrameReceiveStateIncomplete;
  header_ptr->total_packets_received = 0;
  header_ptr->total_sof_marker_count = 0;
  header_ptr->total_eof_marker_count = 0;

  header_ptr->num_active_fems = num_active_fems_;
  for (ExcaliburDecoderFemMap::iterator it = fem_port_map_.begin();
        it != fem_port_map_.end(); ++it)
  {
    header_ptr->active_fem_idx[(it->second).buf_idx_] = (it->second).fem_idx_;
  }
  memset(header_ptr->fem_rx_state, 0,
      sizeof(Excalibur::FemReceiveState) * Excalibur::max_num_fems);

  gettime(reinterpret_cast<struct timespec*>(&(header_ptr->frame_start_time)));

}

void* ExcaliburFrameDecoder::get_next_payload_buffer(void) const
{

  uint8_t* next_receive_location;

  if (current_packet_fem_map_.fem_idx_ != ILLEGAL_FEM_IDX)
  {
    std::size_t subframe_size = Excalibur::subframe_size(asic_counter_bit_depth_);

    next_receive_location = reinterpret_cast<uint8_t*>(current_frame_buffer_)
          + get_frame_header_size ()
          + (subframe_size * Excalibur::num_subframes * current_packet_fem_map_.buf_idx_)
          + (subframe_size * (get_subframe_counter() % 2))
          + (Excalibur::primary_packet_size * get_packet_number());
  }
  else
  {
    next_receive_location = reinterpret_cast<uint8_t*>(ignored_packet_buffer_.get());
  }

  return reinterpret_cast<void*>(next_receive_location);
}

size_t ExcaliburFrameDecoder::get_next_payload_size(void) const
{
  size_t next_receive_size = 0;

  if (get_packet_number() < Excalibur::num_primary_packets[asic_counter_bit_depth_])
  {
    next_receive_size = Excalibur::primary_packet_size;
  }
  else
  {
    next_receive_size = Excalibur::tail_packet_size[asic_counter_bit_depth_];
  }

  return next_receive_size;
}

FrameDecoder::FrameReceiveState ExcaliburFrameDecoder::process_packet(size_t bytes_received)
{

  FrameDecoder::FrameReceiveState frame_state = FrameDecoder::FrameReceiveStateIncomplete;

  // Only process the packet if it is not being ignored due to an illegal port to FEM index mapping
  if (current_packet_fem_map_.fem_idx_ != ILLEGAL_FEM_IDX)
  {

    // If this packet is the last in subframe (i.e. has on EOF marker in the header), extract the
    // frame number (which counts from 1) from the subframe trailer where present, update and/or
    // validate in the frame buffer header appropriately.

    if (get_end_of_frame_marker())
    {

      uint32_t frame_number;

      if ((asic_counter_bit_depth_ == Excalibur::bitDepth24) &&
          ((current_shadow_frame_number_ % 2) == 1))
      {
        LOG4CXX_DEBUG_LEVEL(3, logger_, "Using current shadow frame number "
                            << current_shadow_frame_number_ << " for C0 frame in 24-bit mode");
        frame_number = current_shadow_frame_number_;
      }
      else if (has_subframe_trailer_)
      {
        size_t payload_bytes_received = bytes_received - sizeof(Excalibur::PacketHeader);

        Excalibur::SubframeTrailer* trailer =
            reinterpret_cast<Excalibur::SubframeTrailer*>((uint8_t*) get_next_payload_buffer()
                + payload_bytes_received - sizeof(Excalibur::SubframeTrailer));

        frame_number = static_cast<uint32_t>((trailer->frame_number & 0xFFFFFFFF) - 1);
        LOG4CXX_DEBUG_LEVEL(3, logger_, "Subframe EOF trailer has frame number = " << frame_number);
      }
      else
      {
        LOG4CXX_DEBUG_LEVEL(3, logger_, "No subframe EOF trailer present in this reaodut mode, "
                            << "using current shadow frame number: " << current_shadow_frame_number_);
        frame_number = current_shadow_frame_number_;
      }

      uint32_t subframe_idx = get_subframe_counter() % 2;

      if ((current_frame_header_->frame_number == Excalibur::default_frame_number) &&
          (subframe_idx == 0))
      {
        current_frame_header_->frame_number = frame_number;
      }
      else
      {
        if (frame_number != current_frame_header_->frame_number)
        {
          LOG4CXX_WARN(logger_, "Subframe EOF trailer frame number mismatch for frame "
              << current_frame_seen_ << ": got " << frame_number
              << " from FEM " << current_packet_fem_map_.fem_idx_
              << ", expected " << current_frame_header_->frame_number);
        }
      }
    }

    // Get a convenience pointer to the FEM receive state data in the frame header
    Excalibur::FemReceiveState* fem_rx_state =
        &(current_frame_header_->fem_rx_state[current_packet_fem_map_.buf_idx_]);

    // Increment the total and per-FEM packet received counters
    (fem_rx_state->packets_received)++;
    current_frame_header_->total_packets_received++;

    // If we have received the expected number of packets, perform end of frame processing
    // and hand off the frame for downstream processing.
    if (current_frame_header_->total_packets_received ==
        (Excalibur::num_fem_frame_packets(asic_counter_bit_depth_) * num_active_fems_))
    {

      // Check that the appropriate number of SOF and EOF markers (one each per subframe) have
      // been seen, otherwise log a warning

      if ((current_frame_header_->total_sof_marker_count !=
          (Excalibur::num_subframes * num_active_fems_))
          || (current_frame_header_->total_eof_marker_count !=
              (Excalibur::num_subframes * num_active_fems_)))
      {
        LOG4CXX_WARN(logger_, "Incorrect number of SOF ("
           << (int)current_frame_header_->total_sof_marker_count << ") or EOF ("
           << (int)current_frame_header_->total_eof_marker_count << ") markers "
           << "seen on completed frame " << current_frame_seen_);
      }

      // Set frame state accordingly
      frame_state = FrameDecoder::FrameReceiveStateComplete;

      // Complete frame header
      current_frame_header_->frame_state = frame_state;

      if (!dropping_frame_data_)
      {
        // Erase frame from buffer map
        frame_buffer_map_.erase(current_frame_seen_);

        // Erase counter from shadow frame counter map
        shadow_frame_counter_map.erase(current_frame_seen_);

        // Notify main thread that frame is ready
        ready_callback_(current_frame_buffer_id_, current_frame_header_->frame_number);

        // Reset current frame seen ID so that if next frame has same number (e.g. repeated
        // sends of single frame 0), it is detected properly
        current_frame_seen_ = -1;
      }
    }
  }
  return frame_state;
}

void ExcaliburFrameDecoder::monitor_buffers(void)
{

  int frames_timedout = 0;
  struct timespec current_time;

  gettime(&current_time);

  // Loop over frame buffers currently in map and check their state
  std::map<int, int>::iterator buffer_map_iter = frame_buffer_map_.begin();
  while (buffer_map_iter != frame_buffer_map_.end())
  {
    int frame_num = buffer_map_iter->first;
    int buffer_id = buffer_map_iter->second;
    void* buffer_addr = buffer_manager_->get_buffer_address(buffer_id);
    Excalibur::FrameHeader* frame_header = reinterpret_cast<Excalibur::FrameHeader*>(buffer_addr);

    if (elapsed_ms(frame_header->frame_start_time, current_time) > frame_timeout_ms_)
    {
      LOG4CXX_DEBUG_LEVEL(1, logger_, "Frame " << frame_num << " in buffer " << buffer_id
          << " addr 0x" << std::hex
          << buffer_addr << std::dec << " timed out with " << frame_header->total_packets_received
          << " packets received");

      frame_header->frame_state = FrameReceiveStateTimedout;
      ready_callback_(buffer_id, frame_num);
      frames_timedout++;

      frame_buffer_map_.erase(buffer_map_iter++);
      shadow_frame_counter_map.erase(frame_num);
    }
    else
    {
      buffer_map_iter++;
    }
  }
  if (frames_timedout)
  {
    LOG4CXX_WARN(logger_, "Released " << frames_timedout << " timed out incomplete frames");
  }
  frames_timedout_ += frames_timedout;

  LOG4CXX_DEBUG_LEVEL(2, logger_,  get_num_mapped_buffers() << " frame buffers in use, "
      << get_num_empty_buffers()
      << " empty buffers available, " << frames_timedout_ << " incomplete frames timed out");

}

uint32_t ExcaliburFrameDecoder::get_subframe_counter(void) const
{
  return reinterpret_cast<Excalibur::PacketHeader*>(current_packet_header_.get())->subframe_counter;
}

uint32_t ExcaliburFrameDecoder::get_packet_number(void) const
{
  return reinterpret_cast<Excalibur::PacketHeader*>(
      current_packet_header_.get())->packet_number_flags & Excalibur::packet_number_mask;
}

bool ExcaliburFrameDecoder::get_start_of_frame_marker(void) const
{
  uint32_t packet_number_flags =
      reinterpret_cast<Excalibur::PacketHeader*>(current_packet_header_.get())->packet_number_flags;
  return ((packet_number_flags & Excalibur::start_of_frame_mask) != 0);
}

bool ExcaliburFrameDecoder::get_end_of_frame_marker(void) const
{
  uint32_t packet_number_flags =
      reinterpret_cast<Excalibur::PacketHeader*>(current_packet_header_.get())->packet_number_flags;
  return ((packet_number_flags & Excalibur::end_of_frame_mask) != 0);
}

unsigned int ExcaliburFrameDecoder::elapsed_ms(struct timespec& start, struct timespec& end)
{

  double start_ns = ((double) start.tv_sec * 1000000000) + start.tv_nsec;
  double end_ns = ((double) end.tv_sec * 1000000000) + end.tv_nsec;

  return (unsigned int)((end_ns - start_ns) / 1000000);
}

//! Parse the port to FEM index map configuration string.
//!
//! This method parses a configuration string containing port to FEM index mapping information,
//! which is expected to be of the format "port:idx,port:idx" etc. The map is saved in a member
//! variable for use in packet handling.
//!
//! \param[in] fem_port_map_str - string of port to FEM index mapping configuration
//! \return number of valid map entries parsed from string
//!
std::size_t ExcaliburFrameDecoder::parse_fem_port_map(const std::string fem_port_map_str)
{
    // Clear the current map
    fem_port_map_.clear();

    // Define entry and port:idx delimiters
    const std::string entry_delimiter(",");
    const std::string elem_delimiter(":");

    // Vector to hold entries split from map
    std::vector<std::string> map_entries;

    // Split into entries
    boost::split(map_entries, fem_port_map_str, boost::is_any_of(entry_delimiter));

    unsigned int buf_idx = 0;
    // Loop over entries, further splitting into port / fem index pairs
    for (std::vector<std::string>::iterator it = map_entries.begin(); it != map_entries.end(); ++it)
    {
        if (buf_idx >= Excalibur::max_num_fems) {
          LOG4CXX_WARN(logger_, "Decoder FEM port map configuration contains too many elements, "
                        << "truncating to maximium number of FEMs allowed ("
                        << Excalibur::max_num_fems << ")");
          break;
        }

        std::vector<std::string> entry_elems;
        boost::split(entry_elems, *it, boost::is_any_of(elem_delimiter));

        // If a valid entry is found, save into the map
        if (entry_elems.size() == 2) {
            int port = static_cast<int>(strtol(entry_elems[0].c_str(), NULL, 10));
            int fem_idx = static_cast<int>(strtol(entry_elems[1].c_str(), NULL, 10));
            fem_port_map_[port] = ExcaliburDecoderFemMapEntry(fem_idx, buf_idx);
            buf_idx++;
        }
    }

    // Return the number of valid entries parsed
    return fem_port_map_.size();
}

//! Parse the ASIC counter bit depth configuration string.
//!
//! This method parses a configurationg string specifying the EXCALIBUR ASIC counter bit
//! depth currently in use, returning an enumerated constant for use in the decoder.
//!
//! \param[in] bit_depth_str - string of the bit depth
//! \return enumerated constant defining bit depth, or unknown if the string is not recognised
//!
Excalibur::AsicCounterBitDepth ExcaliburFrameDecoder::parse_bit_depth(
    const std::string bit_depth_str)
{

  //! Set the default bit depth to return to unknown
  Excalibur::AsicCounterBitDepth bit_depth = Excalibur::bitDepthUnknown;

  // Initialise a mapping of string to bit depth
  static std::map<std::string, Excalibur::AsicCounterBitDepth>bit_depth_map;
  if (bit_depth_map.empty())
  {
    bit_depth_map[asic_bit_depth_str_[Excalibur::bitDepth1]]  = Excalibur::bitDepth1;
    bit_depth_map[asic_bit_depth_str_[Excalibur::bitDepth6]]  = Excalibur::bitDepth6;
    bit_depth_map[asic_bit_depth_str_[Excalibur::bitDepth12]] = Excalibur::bitDepth12;
    bit_depth_map[asic_bit_depth_str_[Excalibur::bitDepth24]] = Excalibur::bitDepth24;
  }

  // Set the bit depth value if present in the map
  if (bit_depth_map.count(bit_depth_str))
  {
    bit_depth = bit_depth_map[bit_depth_str];
  }

  return bit_depth;
}
